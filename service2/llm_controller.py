"""硅基流视觉识别：只处理图像与标注，不连接 GDK，不控制机器人。"""
import base64
import io
import json
import math
import os
from pathlib import Path
import uuid

import requests
from PIL import Image, ImageDraw, ImageOps


class LlmController:
    def __init__(self, project_dir=None):
        self.root = Path(project_dir or Path(__file__).resolve().parents[1]).resolve()

    def _config(self):
        config = json.loads((self.root / "data/llm.json").read_text(encoding="utf-8"))
        key = os.environ.get("SILICONFLOW_API_KEY", "")
        secret = self.root / "data/llm.secret.json"
        if not key and secret.exists():
            key = json.loads(secret.read_text(encoding="utf-8")).get("api_key", "")
        if not key:
            raise RuntimeError("未配置 SILICONFLOW_API_KEY 或 data/llm.secret.json")
        # 避免编辑配置后把密钥发送到任意外部地址。
        if config.get("base_url", "").rstrip("/") != "https://api.siliconflow.cn/v1":
            raise ValueError("base_url 必须为硅基流官方 HTTPS API")
        return config, key

    def _image_path(self, filename):
        path = Path(filename)
        if not path.is_absolute():
            path = self.root / "images" / path
        path = path.resolve()
        allowed = [(self.root / folder).resolve() for folder in ("images", "image")]
        if not any(path.is_relative_to(folder) for folder in allowed):
            raise ValueError("只允许识别项目 images/ 或 image/ 下的图片")
        if not path.is_file() or path.stat().st_size > 12 * 1024 * 1024:
            raise ValueError("图片不存在或超过 12 MB")
        return path

    def _parse_result(self, content):
        if not isinstance(content, str) or not content.strip():
            raise ValueError("模型没有返回最终 JSON，请检查 token 限制")
        text = content.strip()
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:-1]).strip()
        result = json.loads(text)
        if not isinstance(result, dict) or type(result.get("found")) is not bool:
            raise ValueError("模型 JSON 缺少 found 布尔值")
        confidence = result.get("confidence", 0)
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("模型置信度无效")
        points = result.get("points", [])
        if not result["found"]:
            points = []
        elif (not isinstance(points, list) or len(points) != 2 or
              any(not isinstance(p, list) or len(p) != 2 or
                  any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1000 for v in p)
                  for p in points)):
            raise ValueError("模型线段坐标必须是 0～1000 范围内的两个端点")
        elif math.dist(points[0], points[1]) < 1:
            raise ValueError("模型返回了退化线段")
        return {"found": result["found"], "points": sorted(points),
                "confidence": confidence, "description": str(result.get("description", ""))[:1000]}

    def _annotate(self, image, result):
        width, height = image.size
        points = [[round(x * (width - 1) / 1000), round(y * (height - 1) / 1000)]
                  for x, y in result["points"]]
        result["pixel_points"] = points
        result["width"], result["height"] = width, height
        draw = ImageDraw.Draw(image)
        if result["found"]:
            start, end = map(tuple, points)
            draw.line([start, end], fill="white", width=9)
            draw.line([start, end], fill="#00499d", width=5)
            for x, y in points:
                draw.ellipse((x-5, y-5, x+5, y+5), fill="#00499d", outline="white", width=2)
            dx, dy = end[0] - start[0], end[1] - start[1]
            result["slope"] = dy / dx if dx else None
            result["angle_deg"] = math.degrees(math.atan2(dy, dx))
            draw.text((10, 10), f"LLM estimate | angle={result['angle_deg']:.2f} deg", fill="#00499d", stroke_width=1, stroke_fill="white")
        else:
            draw.text((10, 10), "Target not found", fill="#00499d", stroke_width=1, stroke_fill="white")
        output = self.root / "image/llm"
        output.mkdir(parents=True, exist_ok=True)
        path = output / f"line-{uuid.uuid4().hex}.jpg"
        image.save(path, "JPEG", quality=92)
        result["output_file"] = str(path)
        result["image"] = base64.b64encode(path.read_bytes()).decode("ascii")
        return result

    def detect_file(self, filename, prompt_id=None):
        config, key = self._config()
        path = self._image_path(filename)
        prompt_id = prompt_id or config.get("default_prompt", "line")
        if prompt_id not in config["prompts"]:
            raise ValueError("未知 prompt_id，请编辑 data/llm.json")
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        if image.width * image.height > 24_000_000:
            raise ValueError("图片尺寸过大")
        encoded = io.BytesIO()
        image.save(encoded, "JPEG", quality=90)
        data_url = "data:image/jpeg;base64," + base64.b64encode(encoded.getvalue()).decode("ascii")
        body = {"model": config["model"], "stream": False,
                "max_tokens": int(config.get("max_tokens", 4096)),
                "messages": [{"role": "system", "content": config["system_prompt"]},
                             {"role": "user", "content": [
                                 {"type": "text", "text": config["prompts"][prompt_id]},
                                 {"type": "image_url", "image_url": {"url": data_url}}]}]}
        try:
            response = requests.post(config["base_url"].rstrip("/") + "/chat/completions",
                                     headers={"Authorization": "Bearer " + key}, json=body,
                                     timeout=(10, min(120, float(config.get("timeout_seconds", 90)))))
        except requests.exceptions.SSLError as error:
            raise RuntimeError("HTTPS 证书校验失败，请检查机器人时间；不会禁用 TLS 校验") from error
        except requests.RequestException as error:
            raise RuntimeError("硅基流网络连接失败或超时") from error
        if response.status_code != 200:
            raise RuntimeError(f"硅基流 API HTTP {response.status_code}；请检查密钥、模型权限或额度")
        reply = response.json()
        choice = reply["choices"][0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("模型输出被截断，请增加 data/llm.json 中的 max_tokens")
        result = self._parse_result(choice["message"].get("content"))
        result.update(model=config["model"], prompt_id=prompt_id, file=str(path),
                      usage=reply.get("usage", {}), warning="模型估算，仅供观察，不用于直接控制机器人")
        return self._annotate(image, result)
