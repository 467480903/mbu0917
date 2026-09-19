services 文件夹中， 新建一个 服务程序， apriltag.py , 它启动的时候， 将使用 .venv-apriltag 的 python 环境，  
  
它会监听 mqtt 报文 /humanoid/apriltag 这个topic ,   如果收到  cmd: detect2tagsForLineDistance, imgPath: /data/wxf/mbu0917/images/, resultSavePath:  /data/wxf/mbu0917/detect

 

 

它就会去读取图片  kHeadColor_latest.jpg   ， 检测， 然后把检测结果放在  resultSave 的目录里， 

 

检测结果要包含：

 

两张tag 区域在图片上的中心点坐标， 

两个tag区的中线点连线的斜率， 

两个tag区的连线的中点

画一条垂直的经过中点的线， 白色

画一条垂直的图像的中心线， 黑色

画一条水平的图像中心线， 黑色，

三条线只要2px像素，

计算两条垂直线水平距离

然后再读取 kHeadDepth_raw_latest.raw  里， 两个 tag 区域中心点，各自附近 3*3 个像素点的深度的平均值， 

 

然后把检测结果命名保存， detect2tagsForLineDistance_年月日时秒毫秒.json 

 

detect2tagsForLineDistance_年月日时秒毫秒.jpg ， 图片上要绘制出 tag 识别区域，两个tag中心点， 中心点连线， 黑白两条垂直线， 图片左上角要显示连线的斜率（弧度值）， 两个 tag区域深度值的平均值， 黑白线的水平距离， 

 

同时， 也要保存 detect2tagsForLineDistance_latest. json / jpg

执行结束后， 往   /humanoid/apriltag/done 发送  {cmd:done,time:年月日时秒毫秒}