#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_controller.py — 数据同步控制器（S7 / Modbus）

职责（参考 agents.md「数据同步」）：
  - 读取 datas/s7.json、datas/modbus.json 配置文件（只做参数读取，不做设备/点位增删）
  - 周期性读取只读点位，存储到内存数据表
  - 可写点位：初始化时写入默认值，之后周期扫描 isChanged==1 的点位写回设备
  - 通过 MQTT 命令读写内存数据表：
      {cmd:readData, name:m1}            → 从内存取值并发布到数据 topic
      {cmd:setData, name:m2, value:112}  → 改内存值并标记 isChanged=1

数据表条目结构（内存）：
  {name: str, type: "read"/"write", value: 任意, isChanged: int(0/1)}
    read  点位：value 由设备周期读取刷新，isChanged 恒为 0
    write 点位：value 为期望值，isChanged=1 表示待写入设备，写回后置 0

不涉及机器人运动，使用 .venv-sync 虚拟环境（含 python-snap7 / Modbus 库）。
"""

import os
import re
import json
import time
import struct
import socket
import threading

try:
    import snap7
    from snap7.client import Client as Snap7Client
    from snap7.util import get_bool, set_bool
    HAS_SNAP7 = True
except ImportError:
    HAS_SNAP7 = False


class SyncController:
    """数据同步控制器（S7 / Modbus）"""

    TOPIC_DATA = "/humanoid/sync/data"

    _PREFIX_SIZE = {"B": 1, "W": 2, "D": 4}
    _ADDR_RE = re.compile(r"^DB(\d+)\.DB([BWD])(\d+)$", re.IGNORECASE)
    _ADDR_BIT_RE = re.compile(r"^DB(\d+)\.DBX(\d+)\.(\d+)$", re.IGNORECASE)

    def __init__(self, mqtt_client, topic_response, config_dir, topic_data=None):
        """构造函数

        Parameters
        ----------
        mqtt_client : mqtt.Client
            MQTT 客户端（可为 None，用于纯本地测试）
        topic_response : str
            反馈主题
        config_dir : str
            配置目录（存放 modbus.json / s7.json）
        topic_data : str, optional
            数据输出主题（readData 结果发布到此主题）
        """
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self.config_dir = config_dir
        self.topic_data = topic_data or self.TOPIC_DATA

        self._devices = []          # 设备配置列表（只读，来自 json）
        self._data = {}             # 数据表 name -> item
        self._lock = threading.Lock()
        self._modbus_tx_id = 0
        self._thread_running = False
        self._thread = None

    # ═══════════════════════════════════════════════════════════
    #  数据表管理
    # ═══════════════════════════════════════════════════════════

    def _data_add(self, name, type_, value=0):
        """向数据表添加点位；write 点位初始 isChanged=1（待写默认值）"""
        with self._lock:
            self._data[name] = {
                "name": name,
                "type": type_,
                "value": value,
                "isChanged": 1 if type_ == "write" else 0,
            }

    def _get_value(self, name):
        """从内存数据表取值（内部使用，不发布）"""
        with self._lock:
            item = self._data.get(name)
            return item.get("value") if item else None

    def _update_read(self, name, value):
        """设备周期读取后刷新 read 点位内存值"""
        with self._lock:
            item = self._data.get(name)
            if item and item["type"] == "read":
                item["value"] = value
                return True
        return False

    def _mark_written(self, name):
        """write 点位成功写入设备后 isChanged 置 0"""
        with self._lock:
            item = self._data.get(name)
            if item and item["type"] == "write":
                item["isChanged"] = 0
                return True
        return False

    def _pending_writes(self):
        """返回所有 isChanged==1 的 write 点位（浅拷贝）"""
        with self._lock:
            return [dict(item) for item in self._data.values()
                    if item["type"] == "write" and item["isChanged"] == 1]

    def read_data(self, name):
        """读取内存点位值并发布到数据 topic（对应 {cmd:readData,name:...}）"""
        value = self._get_value(name)
        self._publish_data({"cmd": "readData", "name": name, "value": value})
        return value

    def set_data(self, name, value):
        """修改写点位内存值并标记 isChanged=1（对应 {cmd:setData,...}）"""
        with self._lock:
            item = self._data.get(name)
            if not item or item["type"] != "write":
                return False
            item["value"] = value
            item["isChanged"] = 1
        return True

    def snapshot(self):
        """返回数据表快照：[{name,type,value,isChanged}, ...]"""
        with self._lock:
            return [{"name": i["name"], "type": i["type"],
                     "value": i["value"], "isChanged": i["isChanged"]}
                    for i in self._data.values()]

    # ═══════════════════════════════════════════════════════════
    #  Modbus TCP（纯 socket，无第三方依赖）
    # ═══════════════════════════════════════════════════════════

    def _modbus_send_recv(self, ip, port, unit_id, pdu, timeout=1.0):
        """构建 MBAP 报文并发送/接收，返回 PDU 响应"""
        self._modbus_tx_id = (self._modbus_tx_id + 1) & 0xFFFF
        mbap = struct.pack(">HHHB", self._modbus_tx_id, 0x0000, len(pdu) + 1, unit_id)
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((ip, port))
            sock.sendall(mbap + pdu)
            header = self._recv_exact(sock, 7)
            if not header:
                return None
            _, _, length, _ = struct.unpack(">HHHB", header)
            return self._recv_exact(sock, length - 1)
        except Exception:
            return None
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    @staticmethod
    def _recv_exact(sock, n):
        """精确读取 n 字节"""
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    @staticmethod
    def _group_continuous(addresses):
        """将地址列表分组为连续段 [(start, count), ...]"""
        if not addresses:
            return []
        addrs = sorted(set(addresses))
        groups = []
        start = addrs[0]
        prev = addrs[0]
        for a in addrs[1:]:
            if a == prev + 1:
                prev = a
            else:
                groups.append((start, prev - start + 1))
                start = a
                prev = a
        groups.append((start, prev - start + 1))
        return groups

    def _modbus_read_holding_registers(self, ip, port, start, count, unit_id=1):
        """读取保持寄存器（功能码 0x03）"""
        pdu = struct.pack(">BHH", 0x03, start, count)
        resp = self._modbus_send_recv(ip, port, unit_id, pdu)
        if not resp or len(resp) < 2 or resp[0] & 0x80:
            return None
        byte_count = resp[1]
        values = []
        for i in range(0, byte_count, 2):
            values.append(struct.unpack(">H", resp[2 + i:4 + i])[0])
        return values

    def _modbus_write_holding_register(self, ip, port, addr, value, unit_id=1):
        """写单个保持寄存器（功能码 0x06）"""
        pdu = struct.pack(">BHH", 0x06, addr, value & 0xFFFF)
        resp = self._modbus_send_recv(ip, port, unit_id, pdu)
        if not resp or len(resp) < 5 or resp[0] & 0x80:
            return False
        return True

    # ═══════════════════════════════════════════════════════════
    #  S7 协议（基于 python-snap7）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def parse_s7_addr(addr):
        """解析 S7 地址 → (db_number, start_byte, size_bytes, bit)

        支持格式：
          DB1.DBW0   → (1, 0, 2, None)   Word
          DB1.DBD0   → (1, 0, 4, None)   DWord
          DB1.DBB0   → (1, 0, 1, None)   Byte
          DB8.DBX2.1 → (8, 2, 1, 1)      Bit（bool）
        """
        m = SyncController._ADDR_BIT_RE.match(addr.strip())
        if m:
            db_num = int(m.group(1))
            start = int(m.group(2))
            bit = int(m.group(3))
            if not 0 <= bit <= 7:
                raise ValueError(f"位号超出范围 (0-7): {addr}")
            return db_num, start, 1, bit
        m = SyncController._ADDR_RE.match(addr.strip())
        if not m:
            raise ValueError(f"无法解析 S7 地址: {addr}")
        db_num = int(m.group(1))
        prefix = m.group(2).upper()
        start = int(m.group(3))
        size = SyncController._PREFIX_SIZE[prefix]
        return db_num, start, size, None

    def _s7_connect(self, dev):
        """建立 snap7 连接"""
        if not HAS_SNAP7:
            raise RuntimeError("未安装 python-snap7")
        client = Snap7Client()
        client.connect(dev["ip"], dev["rack"], dev["slot"], dev["port"])
        return client

    def _s7_read_item(self, client, item):
        """读取单个 item 的值"""
        raw = client.db_read(item["db"], item["start"], item["size"])
        bit = item.get("bit")
        if bit is not None:
            return int(get_bool(raw, 0, bit))
        return int.from_bytes(raw, byteorder="big")

    def _s7_write_item(self, client, item, value):
        """写单个 item 的值，返回是否成功"""
        bit = item.get("bit")
        if bit is not None:
            raw = client.db_read(item["db"], item["start"], 1)
            set_bool(raw, 0, bit, bool(int(value)))
            return client.db_write(item["db"], item["start"], raw) == 0
        if isinstance(value, int):
            raw = bytearray(value.to_bytes(item["size"], byteorder="big"))
        else:
            raw = bytearray(value)
        return client.db_write(item["db"], item["start"], raw) == 0

    # ═══════════════════════════════════════════════════════════
    #  配置加载（只读参数）
    # ═══════════════════════════════════════════════════════════

    def load_config(self):
        """加载 modbus.json 与 s7.json，初始化设备与数据表"""
        self._devices = []
        self._data = {}
        self._load_modbus_config()
        self._load_s7_config()
        print(f"[Sync] 已加载 {len(self._devices)} 个设备，{len(self._data)} 个点位")

    def _load_modbus_config(self):
        path = os.path.join(self.config_dir, "modbus.json")
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for dev in raw:
            read_cfg = dev.get("read") or {}
            write_cfg = dev.get("write") or {}
            read_holdings = read_cfg.get("holdings", []) if isinstance(read_cfg, dict) else read_cfg
            read_names = read_cfg.get("names", []) if isinstance(read_cfg, dict) else []
            write_holdings = write_cfg.get("holdings", []) if isinstance(write_cfg, dict) else write_cfg
            write_names = write_cfg.get("names", []) if isinstance(write_cfg, dict) else []
            write_values = write_cfg.get("values", []) if isinstance(write_cfg, dict) else []
            self._devices.append({
                "type": "modbus",
                "name": dev.get("name", ""),
                "ip": dev.get("ip", "127.0.0.1"),
                "port": dev.get("port", 502),
                "read_holdings": list(read_holdings),
                "read_names": list(read_names),
                "write_holdings": list(write_holdings),
                "write_names": list(write_names),
                "rate": dev.get("rate", 1000),
            })
            for i, addr in enumerate(read_holdings):
                name = read_names[i] if i < len(read_names) else f"modbus_r_{addr}"
                self._data_add(name, "read", 0)
            for i, addr in enumerate(write_holdings):
                name = write_names[i] if i < len(write_names) else f"modbus_w_{addr}"
                value = write_values[i] if i < len(write_values) else 0
                self._data_add(name, "write", value)

    def _load_s7_config(self):
        path = os.path.join(self.config_dir, "s7.json")
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for dev in raw:
            read_items = self._parse_s7_items(dev.get("read") or [])
            write_items = self._parse_s7_items(dev.get("write") or [])
            self._devices.append({
                "type": "s7",
                "name": dev.get("name", ""),
                "ip": dev.get("ip", "127.0.0.1"),
                "port": dev.get("port", 102),
                "rack": dev.get("rack", 0),
                "slot": dev.get("slot", 1),
                "read_items": read_items,
                "write_items": write_items,
                "rate": dev.get("rate", 1000),
            })
            for it in read_items:
                self._data_add(it["name"], "read", 0)
            for it in write_items:
                self._data_add(it["name"], "write", it.get("value", 0))

    def _parse_s7_items(self, raw_items):
        """解析 S7 read/write 条目列表"""
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("items", [])
        items = []
        for it in raw_items:
            db_num, start, size, bit = self.parse_s7_addr(it["addr"])
            items.append({
                "name": it["name"], "addr": it["addr"],
                "type": it.get("type", "int"),
                "value": it.get("value", 0),
                "db": db_num, "start": start, "size": size, "bit": bit,
            })
        return items

    # ═══════════════════════════════════════════════════════════
    #  设备读取（周期性刷新 read 点位内存）
    # ═══════════════════════════════════════════════════════════

    def _read_device(self, dev):
        """读取单个设备的只读点位并更新内存数据表"""
        if dev["type"] == "modbus":
            return self._read_modbus_device(dev)
        return self._read_s7_device(dev)

    def _read_modbus_device(self, dev):
        values = {}
        for start, count in self._group_continuous(dev["read_holdings"]):
            vals = self._modbus_read_holding_registers(dev["ip"], dev["port"], start, count)
            if vals:
                for i, addr in enumerate(range(start, start + count)):
                    values[addr] = vals[i]
        read_names = dev.get("read_names", [])
        result = []
        for i, addr in enumerate(dev["read_holdings"]):
            name = read_names[i] if i < len(read_names) else None
            val = values.get(addr)
            if name:
                self._update_read(name, val)
            result.append({"name": name, "address": addr, "value": val})
        return result

    def _read_s7_device(self, dev):
        try:
            client = self._s7_connect(dev)
        except Exception as e:
            print(f"[Sync] S7 连接 {dev['ip']} 失败: {e}")
            return []
        result = []
        try:
            for item in dev.get("read_items", []):
                try:
                    val = self._s7_read_item(client, item)
                except Exception:
                    val = None
                if val is not None:
                    self._update_read(item["name"], val)
                result.append({"name": item["name"], "addr": item["addr"], "value": val})
        finally:
            try:
                client.disconnect()
            except Exception:
                pass
        return result

    # ═══════════════════════════════════════════════════════════
    #  设备写入（isChanged==1 的 write 点位写回设备）
    # ═══════════════════════════════════════════════════════════

    def _process_pending_writes(self):
        """扫描 isChanged==1 的 write 点位并写入对应设备"""
        pending = self._pending_writes()
        if not pending:
            return
        pending_names = {i["name"] for i in pending}
        for dev in self._devices:
            if dev["type"] == "modbus":
                self._process_modbus_writes(dev, pending_names)
            else:
                self._process_s7_writes(dev, pending_names)

    def _process_modbus_writes(self, dev, pending_names):
        write_names = dev.get("write_names", [])
        write_holdings = dev["write_holdings"]
        for i, addr in enumerate(write_holdings):
            name = write_names[i] if i < len(write_names) else None
            if not name or name not in pending_names:
                continue
            value = self._get_value(name)
            ok = self._modbus_write_holding_register(dev["ip"], dev["port"], addr, value)
            if ok:
                self._mark_written(name)
                print(f"[Sync] Modbus 写入 {dev['ip']}:{addr} ({name}) = {value}")
            else:
                print(f"[Sync] Modbus 写入失败 {dev['ip']}:{addr} ({name})")

    def _process_s7_writes(self, dev, pending_names):
        item_map = {it["name"]: it for it in dev.get("write_items", [])}
        if not item_map:
            return
        try:
            client = self._s7_connect(dev)
        except Exception as e:
            print(f"[Sync] S7 写入连接失败 {dev['ip']}: {e}")
            return
        try:
            for name, cfg in item_map.items():
                if name not in pending_names:
                    continue
                value = self._get_value(name)
                ok = self._s7_write_item(client, cfg, value)
                if ok:
                    self._mark_written(name)
                    print(f"[Sync] S7 写入 {dev['ip']} {cfg['addr']} ({name}) = {value}")
                else:
                    print(f"[Sync] S7 写入失败 {dev['ip']} {cfg['addr']} ({name})")
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════
    #  后台轮询线程
    # ═══════════════════════════════════════════════════════════

    def _polling_loop(self):
        """按各设备 rate 周期读取只读点位 + 周期写入待同步 write 点位"""
        print("[Sync] 轮询线程已启动")
        next_times = {}
        write_interval = 0.05
        last_write = 0.0
        while self._thread_running:
            now = time.time()
            with self._lock:
                devices = list(self._devices)
            for dev in devices:
                key = (dev["type"], dev["ip"])
                if now >= next_times.get(key, 0.0):
                    try:
                        self._read_device(dev)
                    except Exception as e:
                        print(f"[Sync] 读取 {dev['ip']} 失败: {e}")
                    next_times[key] = now + dev.get("rate", 1000) / 1000.0
            if now - last_write >= write_interval:
                last_write = now
                try:
                    self._process_pending_writes()
                except Exception as e:
                    print(f"[Sync] 写入扫描失败: {e}")
            time.sleep(0.01)
        print("[Sync] 轮询线程已停止")

    def start_polling(self):
        """启动后台轮询线程（write 点位默认值随首轮写入下发）"""
        if self._thread_running:
            return
        if not self._devices:
            self.load_config()
        self._thread_running = True
        self._thread = threading.Thread(target=self._polling_loop, daemon=True)
        self._thread.start()

    def stop_polling(self):
        """停止后台轮询线程"""
        self._thread_running = False
        if self._thread:
            self._thread.join(timeout=2)

    # ═══════════════════════════════════════════════════════════
    #  MQTT 发布
    # ═══════════════════════════════════════════════════════════

    def _publish_data(self, payload):
        """发布数据到数据主题"""
        if self.mqtt_client is None:
            return
        self.mqtt_client.publish(self.topic_data, json.dumps(payload, ensure_ascii=False))

    def _publish_response(self, cmd, ts, success=False, extra=None):
        """发布反馈报文"""
        if self.mqtt_client is None:
            return
        resp = {"cmd": cmd, "time": ts}
        if success:
            resp["success"] = True
        if extra:
            resp.update(extra)
        self.mqtt_client.publish(self.topic_response, json.dumps(resp, ensure_ascii=False))
