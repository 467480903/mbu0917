# 主要目标
参考 services/ 下的代码，在这个文件夹 services2/ 里做重构改进
这个代码和智元G2机器人的控制有关

# 主要交互方式

这里主要是创建一些基于 MQTT 的报文通信，
这边的python代码会使用 G2 GDK ，激活机器人的设备驱动层，
然后，根据发送过来的 MQTT 请求报文， 执行设备活动， 等设备动作完成之后， 再反馈动作完成报文

# 测试要求

每个功能模块要能尽量的独立测试，每个模块内部的每个子函数都要有对应的测试文件，做功能单一的测试，测试脚本要尽量简单，20行代码以内
测试时，对于涉及到机器人本体运动的， 执行运动前要提示用户输入回车
由于这里的功能主要是基于 MQTT 报文 交互的，所以，功能测试要尽量以 mqtt pub 命令行为主，
凡是涉及到机器人运动的测试文件， AI agent 不能直接执行，
不涉及机器人运动的， 比如文件操作， 数据库操作， AI agent 可以直接测试对应的测试文件做测试

# 代码风格

防止过度嵌套设计,功能模块里的函数，涉及到 GDK 调用的， 不要嵌套其他子函数， 直接调用功能
每个 controller 文件， 所有变量， 函数， 都被包裹到类里面， 不要 main 函数， 也不要 get_controller 和 handle_request. controler 的构造函数要传参， 把  GDK对象 ， MQTT 对象传进去。 类里面的每个关键功能函数， 都要在 test/services2 目录中， 创建一个测试文件


# 主要功能划分

|名称|功能描述|是否涉及G2运动|mqtt命令是否需要等待判断|需要哪个python环境|
|--|--|--|--|--|
|底盘控制器|既可以蟹行斜走，也可以啊卡曼方式转弯，当然也能直接前后行走|是|是|source ~/app/env.bash|
|数据库控制器|操作一个sqlite数据库，读写里面的 关节角 坐标姿态 地图点位 |不是|不是|默认系统python|
|关节控制器|控制全身关节运动，有 底盘5关节，全身关节22关节， 头部3关节， 左手7关节， 右手7关节 这几种控制方式|是|是|source ~/app/env.bash|
|位姿控制器|控制左右手末端的运动，有 左右手  左手  右手 腰部（上下前后） 这4种运动方式|是|是|source ~/app/env.bash|
|末端控制器|控制末端爪子的张合。|是|是|source ~/app/env.bash|
|交互控制器|控制TTS输出|不是|不是|source ~/app/env.bash|
|摄像头控制器|控制头部摄像头的彩色相机，头部深度相机，左手手腕，右手手腕的视频流输出和拍照保存|不是|是|source ~/app/env.bash|
|apriltag图片解析控制器|对摄像头控制器保存的图片，做识别解析|不是|是|source .venv-apriltag/bin/activate|
|状态发布机|全身关节，左右两个手的末端姿态坐标，夹爪的当前开合值，读取频率5HZ，这些要MQTT发布出去，头部彩色相机和深度相机，还有手腕相机读取，频率3HZ，这些不用MQTT发出去，而是保存在内存中而已|不是|不|source ~/app/env.bash|
|数据同步控制器|读取datas/s7.json  modbus.json配置文件，周期性读取只读点位， 对于可写点位， 在初始化系统的时候写入默认值，然后周期性判断值有没有被外部更新过，如果发现被更新了，就写入。  需要创建一个虚拟环境 sync ， 里面安装 s7 和 MODBUS 库|不是|是|source .venv-sync/bin/activate|



# 底盘控制器

监听地址： /humanoid/base/request/
反馈地址： /humanoid/base/response/
完成信号地址： /humanoid/done/
主要函数


|名称|交互描述|反馈报文|完成报文|
|--|--|--|--|
|相对运动|{cmd:relative,x:10,y:10,rotate:60,time:年月日时分秒毫秒，异步：true} 单位毫米，角度, 基于 GDK relative_move 接口，需要添加 while true 来做到位判断, use slam.get_curr_pose to compare the gap between target|{cmd:relative,time:年月日时分秒毫秒}|{cmd:relative,time:年月日时分秒毫秒,type:base}|
|到点运动|{cmd:point,name:p1,time:年月日时分秒毫秒} 读取数据库中的点位对应的X Y Z RX RY RZ RW，然后使用 GDK normal_navi 函数，因为它支持到点后做重定位。由于这个函数本身是非阻塞的，因此命令下发后要有个while true 来判断是否到达 |{cmd:point,time:年月日时分秒毫秒}|{cmd:point,time:年月日时分秒毫秒,type:base}|
|多点运动|{cmd:points,val:["p1","p2","p3","p4"],vel_line:10,vel_rotate:2,time:年月日时分秒毫秒} 从地图里读取点位，得到每个点位的坐标和旋转，除了最后一个点位使用 normal_navi 做有精度要求的运动，其他点位都用 move_chassis 来走 |{cmd:points,time:年月日时分秒毫秒}|{cmd:points,time:年月日时分秒毫秒,type:base}|
|停止|立刻停止底盘的运动{cmd:stop,time:年月日时分秒毫秒}|--|--|
|相对运动2|{cmd:relative2,x:10,y:10,rotate:60,vel_line:1,vel_rotate:10,time:年月日时分秒毫秒，异步：true} 单位毫米，角度, 基于 GDK move_chassis 接口，需要添加 while true 来做到位判断, use slam.get_curr_pose to compare the gap between target|{cmd:relative2,time:年月日时分秒毫秒}|{cmd:relative2,time:年月日时分秒毫秒,type:base}|

## 相对运动2

这是一个带速度参数的相对运动,
先计算当前位置 X Y 和 目标位置 X Y ，计算出两点的斜率和目标角度朝向， 然后根据当前的角度朝向， 执行转角运动， 转角速度是 vel_rotate
使用 move_chassis 跑的时候，用蟹行的方式走线性运动,
线性运动时，总路程分为12段，前4段分别加速， 后四段分别减速， 中间4段就是目标速度 vel_line （米/秒），
将设置一个 队列 ， 先压入 12段  {持续时间，速度} ， 然后从队列里依次读取，根据持续时间和速度进行运动， 等持续时间到了之后， 就从队列里拉去下一段， 安居持续时间和速度运动， 等最后一段运行完毕之后， 机器就停止。
等运动到目标位置后，再根据当前的角度， 和目标姿态角度， 再执行一次转角，转角速度， 就是 vel_rotate ， 单位 角度/秒

## 多点运动

除了最后一个点位是 到点运动 , 其他的点都通过 相对运动2 来跑，

# 关节控制器

不要在里面加载数据库控制器， 
由于， joint_control_request move_head_joint move_waist_joint move_arm_joint 这几个都是阻塞式运动，所以， 关节控制器里的每一个运动函数， 执行前， 发送 运动命令下发告知，后面都要发  运动到位完成  信号

# apriltag图片解析控制器

它启动的时候，不使用系统的python环境，而使用 .venv-apriltag 这个虚拟的环境

# 数据同步

首先，这个类里面会有类似数据表格：

|名称|类型|值|isChanged|
|--|--|--|--|
|m1|读|111||
|m2|写|112|1|
|m3|写|113|0|

周期性read目标设备的可读点位, 存储在内存中。 若收到  {cmd:readData,name:m1 } 这种 mqtt 报文， 就直接把数据从内存中扫出来， 然后输出到 目标 topic 中。 若收到 {cmd:setData,name:m1,value:111} 这种包文， 就修改内存里的对应变量的值， 然后修改标志位 isChanged=1， 然后等s7和 modbus 这两个类的 周期性write 函数， 把所有的 isChanged==1的可写变量， 写入到设备中，然后把 isChanged = 0

不需要 设备添加删除 的功能。 对于两个 .json 的配置文件， 只做参数读取即可，不需要实现  设备添加删除， 点位添加删除 的功能