1.usb的vid和pid
    打开config文件, 找到<usb ..../>项, 修改其中的vid和pid, 如果要忽略vid或pid, 则填0,如果要忽略interface和subdevice则填-1

2.修改语言类型
    打开config文件, 找到<local ..../>项, 修改其中的language的值为"cn"或则"en"

3.修改/添加/删除媒体按键Media Key的列表和键值
    打开config文件, 找到<mediakey>...</mediakey>项, 修改/添加/删除其中的子项<key .../>, 其中name为列表显示内容, code为键值

4.修改/添加/删除功能按键Function Key的列表和键值
    打开config文件, 找到<functkey>...</functkey>项, 修改/添加/删除其中的子项<key .../>, 其中name为列表显示内容, code为键值,
    code可为多个键值的组合, 但必须用英文逗号','隔开

5.添加翻译
    英文翻译: 默认为EN文, 所以无需添加
    中文翻译: 打开uires\Translator\lang_cn.xml文件, 在<context>...</context>之间添加对应的翻译项, source为原文, translation为译文

6.修改/添加/删除按键
    打开positions.xml文件按照对应格式修改, rect为按键范围, id为键值, color按键背景颜色, name可以忽略

    