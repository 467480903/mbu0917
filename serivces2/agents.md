# 主要目标
参考 services/ 下的代码，做重构改进
这个代码和智元G2机器人的控制有关

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
|apriltag图片解析控制器|对摄像头控制器保存的图片，做识别解析|不是|是|source ~/app/env.bash|source .venv-apriltag/bin/activate|

# 底盘控制器

监听地址： /humanoid/base/request/
反馈地址： /humanoid/base/response/
完成信号地址： /humanoid/done/
主要函数


|名称|收到报文|反馈报文|完成报文|
|--|--|--|--|
|前后|{cmd:FB,val:100，vel:50,time:年月日时分秒毫秒，异步：} 单位毫米，前+ 后-, 基于 GDK 里程计接口|{cmd:FB,time:年月日时分秒毫秒}|{cmd:FB,time:年月日时分秒毫秒,type:base}|
|左右|{cmd:RL,val:100，vel:50,time:年月日时分秒毫秒} 单位毫米，左+ 右-, 基于 GDK 里程计接口|{cmd:RL,time:年月日时分秒毫秒}|{cmd:RL,time:年月日时分秒毫秒,type:base}|
|旋转|{cmd:rotate,val:45，vel:50,time:年月日时分秒毫秒} 单位角度，顺时针 + , 基于 GDK 里程计接口|{cmd:rotate,time:年月日时分秒毫秒}|{cmd:rotate,time:年月日时分秒毫秒,type:base}|
|到点运动|{cmd:point,val:1,time:年月日时分秒毫秒} 从地图里读取点位，然后使用 GDK MAP里的功能走 |{cmd:point,time:年月日时分秒毫秒}|{cmd:point,time:年月日时分秒毫秒,type:base}|
|蟹行|{cmd:crab,x:100,y:100,time:年月日时分秒毫秒} 使用 GDK PNC 接口 |{cmd:crab,time:年月日时分秒毫秒}|{cmd:crab,time:年月日时分秒毫秒,type:base}|
|多点运动|{cmd:waypoints,val:[1,2,3,4],time:年月日时分秒毫秒} 从地图里读取点位，然后使用 GDK MAP里的功能走 |{cmd:waypoints,time:年月日时分秒毫秒}|{cmd:waypoints,time:年月日时分秒毫秒,type:base}|