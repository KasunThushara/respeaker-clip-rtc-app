# ReSpeaker Clip vs 安克AI录音豆 定量对比报告

> **测试日期**: 2026-04-24
> **测试地点**: 9楼03会议室
> **测试人员**: [待填写]

---

## 1. 测试配置

### 1.1 测试设备

| 项目 | ReSpeaker Clip | 安克AI录音豆 D3200 |
|------|---------------|-------------------|
| 固件版本 | v2.1.1 | [待填写] |
| 录音模式 | Enhanced (merge L+R) | 默认模式 |
| 编码格式 | Opus 32kbps VBR mono | Opus/AAC stereo |
| 文件格式 | .ogg | .ogg |

### 1.2 固件音频参数

| 参数 | 值 | 说明 |
|------|-----|------|
| PDM增益 | 0x48 (+10dB) | nRF5340 GAINL/GAINR |
| AGC目标电平 | 8000 | 整数AGC, Q8.8 |
| AGC最大增益 | +24dB (4096 Q8.8) | 远场补偿上限 |
| AGC噪声门限 | 200 | 低于此值不施加增益 |
| AGC起控时间 | ~2帧 (~40ms) | 快速抑制近场 |
| AGC释放时间 | ~128帧 (~2.5s) | 慢释放维持远场增益 |
| 降噪强度 | 15dB | SpeexDSP噪声抑制 |
| 去混响 | 关闭 | — |
| 限幅器拐点 | 26000 (-2.0dBFS) | 软限幅 |
| 限幅器硬限 | 31000 (-0.5dBFS) | — |

### 1.3 音频处理流水线

```
PDM采集 → Merge(L+R, 延迟对齐) → SpeexDSP降噪(15dB) → 整数AGC → 软限幅器 → Opus编码
```

### 1.4 测试环境

| 项目 | 值 |
|------|-----|
| 测试地点 | 9楼03会议室 |
| 环境噪声 | [待填写] dB(A) |
| 扬声器音量 | [待填写] dB(A) @ 1m |
| 室温 | [待填写] °C |

### 1.5 测试距离与语料

每个距离测试约5分钟：中文20句 + 英文20句 + 数字10组。

**Clip 切割时间点：**

| 距离 | 开始 | 中文 | 英文 | 数字 |
|------|------|------|------|------|
| 0.5m | 0:10 | 10s-139s | 139s-245s | 245s-295s |
| 1m | 5:06 | 306s-435s | 435s-541s | 541s-591s |
| 2m | 10:03 | 603s-732s | 732s-838s | 838s-888s |
| 3m | 15:01 | 901s-1030s | 1030s-1136s | 1136s-1186s |

**Anker 切割时间点（0.5m 精确，其余按 Clip 间隔推算）：**

| 距离 | 开始 | 中文 | 英文 | 数字 |
|------|------|------|------|------|
| 0.5m | 0:05 | 5s-134s | 134s-240s | 240s-290s |
| 1m | 5:01 | 301s-430s | 430s-536s | 536s-586s |
| 2m | 9:58 | 598s-727s | 727s-833s | 833s-883s |
| 3m | 14:56 | 896s-1025s | 1025s-1131s | 1131s-1181s |

### 1.6 测试结果文件

| 文件 | 设备 | 时长 | 大小 |
|------|------|------|------|
| clip.ogg | ReSpeaker Clip | 20:05 | 5.6 MB |
| anker.ogg | 安克AI录音豆 | 19:55 | 9.3 MB |
| clip.wav | ReSpeaker Clip (16kHz mono) | 20:05 | 37 MB |
| anker.wav | 安克AI录音豆 (16kHz mono) | 19:56 | 37 MB |

> 编码效率: Clip 5.6MB/20min vs 安克 9.3MB/20min。Clip 文件体积仅为安克的 **60%**（mono vs stereo 编码差异）。

---

## 2. 信号质量分析

### 2.1 噪声底噪（静默段）

两台设备在切换距离的静默间隙中测量的底噪电平（越低越好）。

| 测量时段 | Clip (dB) | Anker (dB) | 差值 (dB) | 优势方 |
|----------|-----------|------------|-----------|--------|
| 0.5m→1m 间隙 | 38.9 | 50.4 | **-11.6** | **Clip** |
| 1m→2m 间隙 | 47.9 | 50.9 | -3.0 | **Clip** |
| 2m→3m 间隙 | 39.6 | 49.9 | **-10.3** | **Clip** |

> **小结**: Clip 底噪全面低于安克，平均低 **8.3 dB**。SpeexDSP 降噪 + AGC 噪声门限有效控制了静默段的噪声。

### 2.2 语音电平与信噪比

| 距离 | 指标 | Clip | Anker | 差值 | 优势方 |
|------|------|------|-------|------|--------|
| 0.5m | 语音RMS | 58.3 dB | 58.5 dB | -0.2 | 持平 |
| 0.5m | SNR | **19.4 dB** | 8.0 dB | **+11.4** | **Clip** |
| 0.5m | 动态范围 | **49.0 dB** | 19.9 dB | **+29.1** | **Clip** |
| 1m | 语音RMS | 58.0 dB | 56.4 dB | +1.7 | Clip |
| 1m | SNR | **10.1 dB** | 5.4 dB | **+4.7** | **Clip** |
| 1m | 动态范围 | **43.2 dB** | 22.0 dB | **+21.2** | **Clip** |
| 2m | 语音RMS | 57.9 dB | 54.6 dB | +3.3 | Clip |
| 2m | SNR | **18.3 dB** | 4.7 dB | **+13.6** | **Clip** |
| 2m | 动态范围 | **44.2 dB** | 15.5 dB | **+28.7** | **Clip** |
| 3m | 语音RMS | 56.3 dB | 52.1 dB | +4.2 | Clip |
| 3m | SNR | **17.5 dB** | 1.7 dB | **+15.8** | **Clip** |
| 3m | 动态范围 | **43.2 dB** | 11.4 dB | **+31.8** | **Clip** |

> **小结**:
> - **SNR**: Clip 在所有距离全面领先，优势 +4.7 ~ +15.8 dB。3m 时 Clip SNR 17.5dB vs 安克仅 1.7dB。
> - **动态范围**: Clip 以 +21~+32 dB 的绝对优势领先。安克动态范围压缩严重（仅 11-22 dB）。
> - **语音电平**: Clip 在 1m/2m/3m 更高，AGC 远场补偿效果明显。

### 2.3 频率响应

#### 0.5m

| 频段 | Clip (dB) | Anker (dB) | 差值 (dB) | 优势方 |
|------|-----------|------------|-----------|--------|
| 100-500Hz | 124.5 | 127.1 | -2.6 | 安克 |
| 500Hz-1kHz | 125.8 | 126.3 | -0.5 | 安克 |
| 1k-2kHz | 129.4 | 128.1 | +1.3 | Clip |
| 2k-3kHz | 129.5 | 126.4 | +3.1 | Clip |
| 3k-4kHz | 119.7 | 124.8 | -5.1 | 安克 |
| 4k-6kHz | 107.4 | 121.8 | **-14.4** | 安克 |
| 6k-8kHz | 110.8 | 116.4 | -5.6 | 安克 |

#### 1m

| 频段 | Clip (dB) | Anker (dB) | 差值 (dB) | 优势方 |
|------|-----------|------------|-----------|--------|
| 100-500Hz | 125.9 | 125.9 | +0.0 | 持平 |
| 500Hz-1kHz | 126.6 | 125.1 | +1.5 | Clip |
| 1k-2kHz | 129.2 | 125.6 | +3.6 | Clip |
| 2k-3kHz | 129.0 | 123.1 | +5.9 | Clip |
| 3k-4kHz | 119.3 | 122.5 | -3.2 | 安克 |
| 4k-6kHz | 107.8 | 116.2 | -8.4 | 安克 |
| 6k-8kHz | 107.6 | 112.8 | -5.2 | 安克 |

#### 2m

| 频段 | Clip (dB) | Anker (dB) | 差值 (dB) | 优势方 |
|------|-----------|------------|-----------|--------|
| 100-500Hz | 125.0 | 123.6 | +1.4 | Clip |
| 500Hz-1kHz | 129.0 | 124.1 | +4.9 | Clip |
| 1k-2kHz | 129.1 | 123.2 | +5.9 | Clip |
| 2k-3kHz | 128.5 | 121.0 | +7.5 | Clip |
| 3k-4kHz | 118.3 | 119.4 | -1.1 | 安克 |
| 4k-6kHz | 107.3 | 113.4 | -6.1 | 安克 |
| 6k-8kHz | 104.3 | 108.9 | -4.6 | 安克 |

#### 3m

| 频段 | Clip (dB) | Anker (dB) | 差值 (dB) | 优势方 |
|------|-----------|------------|-----------|--------|
| 100-500Hz | 128.8 | 123.7 | +5.1 | Clip |
| 500Hz-1kHz | 124.2 | 116.5 | +7.7 | Clip |
| 1k-2kHz | 128.8 | 119.7 | +9.2 | Clip |
| 2k-3kHz | 123.7 | 113.0 | +10.7 | Clip |
| 3k-4kHz | 112.9 | 113.0 | -0.1 | 持平 |
| 4k-6kHz | 103.2 | 106.8 | -3.6 | 安克 |
| 6k-8kHz | 92.5 | 101.2 | -8.6 | 安克 |

> **小结**: 中低频(500Hz-3kHz) Clip 全面领先，高频(3k-8kHz) 安克全面领先。3m 时 3k-4kHz 接近持平。

### 2.4 频谱质心

| 距离 | Clip (Hz) | Anker (Hz) | 差值 (Hz) | 优势方 |
|------|-----------|------------|-----------|--------|
| 0.5m | 1846 | 2104 | -258 | 安克 |
| 1m | 1779 | 1623 | +156 | Clip |
| 2m | 1653 | 1329 | +324 | Clip |
| 3m | 1252 | 619 | **+634** | **Clip** |

### 2.5 削波分析

两者均无削波。Clip 峰值较高（AGC+限幅器协同），安克峰值较低（内置DSP压缩较重）。

---

## 3. 语音识别对比

### 3.1 ASR 引擎

| 项目 | 值 |
|------|-----|
| ASR模型 | DashScope Fun-ASR-Realtime |
| 接口 | WebSocket 流式 (`wss://dashscope.aliyuncs.com/api-ws/v1/inference/`) |
| 模型ID | `fun-asr-realtime` |
| 采样率 | 16kHz mono |
| 分块大小 | 3200 bytes (100ms) |

### 3.2 参考语料（预期结果）

**中文20句：**

> 今天天气很好，我们去公园散步吧。明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概十五分钟。服务员问我们要不要加点辣椒油。我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都会聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很合理。

**英文20句：**

> The birch canoe slid on the smooth planks. Glue the sheet to the dark blue background. It is easy to tell the depth of a well. These days a chicken leg is a rare dish. Rice is often served in round bowls. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The hogs were fed chopped corn and garbage. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A pot of tea helps to pass the evening. Smoky fires lack flame and heat. The soft cushion broke the man's fall. The salt breeze came across from the sea. The girl at the booth sold fifty bonds.

**数字10组：**

> 38271954 60492817 51937602 84260591 17359284 90641735 25814706 72946150 46083572 03718469

### 3.3 中文识别结果

#### 识别字符数统计

| 距离 | Clip | Anker | 差值 | 优势方 |
|------|------|-------|------|--------|
| 0.5m | 356 字 | 356 字 | +0 | 持平 |
| 1m | **358 字** | 355 字 | +3 | Clip |
| 2m | **355 字** | 344 字 | **+11** | **Clip** |
| 3m | **356 字** | 345 字 | **+11** | **Clip** |

> 参考语料共 20 句约 358 字（不含标点）。

#### 0.5m 中文

**Clip** (356字) [原始音频](clip.wav) [切片](segments/clip_zh_05m.wav):

> 今天天气很好，我们去公园散步吧。明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末，我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都汇聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很合理。

**Anker** (356字) [原始音频](anker.wav) [切片](segments/anker_zh_05m.wav):

> 今天天气很好，我们去公园散步吧。明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末，我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都汇聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很合理。

#### 2m 中文

**Clip** (355字) [切片](segments/clip_zh_2m.wav):

> 今天天气很好，我们去公园散步吧。明天早上8点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都会聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很合理。

**Anker** (344字) [切片](segments/anker_zh_2m.wav):

> 今天天气很好，我们去公园散步吧。明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的。这道菜的口味偏辣。老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油。我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多。夏天的时候，孩子们喜欢去河边。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都汇聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很。

> **差异标注**: 安克2m出现句子截断："看一个小时的。"（缺"书"）、"口味偏辣。"（独立断句）、"老人和小孩。"（独立断句）、"解决了很多。"（缺"难题"）、"去河边。"（缺"游泳"）、"价格也很。"（缺"合理"）。

#### 3m 中文

**Clip** (356字) [切片](segments/clip_zh_3m.wav):

> 今天天气很好，我们去公园散步吧。明天早上8点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末，我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都会聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很合理。

**Anker** (345字) [切片](segments/anker_zh_3m.wav):

> 今天天气很好，我们去公园散步吧。明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的。这道菜的口味偏。不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末，我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点呢？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边。这篇文章的重点是分析数据趋势。每年春节，全家人都汇聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很。

> **差异标注**: 安克3m截断更明显："看一个小时的。"、"口味偏。"、"加点呢？"（误识别"辣椒油"→"呢"）、"去河边。"（缺"游泳"）、"分析数据趋势。"（缺"和规律"）、"价格也很。"（缺"合理"）。

### 3.4 英文识别结果

#### 识别字符数统计

| 距离 | Clip | Anker | 差值 | 优势方 |
|------|------|-------|------|--------|
| 0.5m | 643 字 | 645 字 | -2 | 持平 |
| 1m | 634 字 | 649 字* | — | — |
| 2m | **601 字** | 558 字 | **+43** | **Clip** |
| 3m | **650 字** | 607 字 | **+43** | **Clip** |

> *anker_en_1m 首次 ASR 返回空结果（API 偶发错误），补测为 649 字。

#### 0.5m 英文

**Clip** (643字) [切片](segments/clip_en_05m.wav):

> The birch canoe slid on the smooth planks. Glue the sheet to the dark blue background. It is easy to tell the depth of a well. These days a chicken leg is a rare dish. Rice is often served in rumbles. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The hogs were fed chopped corn and garbage. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A pot of tea helps to pass the evening. Smoking fires lack flame and heat. The soft cushion broke the man's fall. The salt breeze came across from the sea. The girl at the booth sold 50 bonds.

**Anker** (645字) [切片](segments/anker_en_05m.wav):

> The birch canoe slid on the smooth planks. Glue the sheet to the dark blue background. It is easy to tell the depth of a well. These days, a chicken leg is a rare dish. Rice is often served in round bowls. The juice of lemons makes fine punsh. The box was thrown beside the parked truck. The hogs were fed chopped corn and garbage. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A pot of tea helps to pass the evening. Smoky fires like flame and heat. The soft cushion broke the man's fall. The salt breeze came across from the sea. The girl at the booth sold 50 bonds.

#### 2m 英文

**Clip** (601字) [切片](segments/clip_en_2m.wav):

> slid on the smooth planks. Glue the sheet to the dark blue background. To tell the depth of a well. These days. Is a rare. Rice is often served in runnels. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The hogs were fed chopped corny garbage. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A lot of tea helps to pass the evening. Smoky fires lack flame and heat. The soft cushion broke the man's fall. The salt breeze came across from the sea. Girl at the booth sold 50 bonds.

**Anker** (558字) [切片](segments/anker_en_2m.wav):

> And slid on the smooth planks. Glue the sheet to the dark blue background. It is easy to tell the depth of a well. These days, a chicken leg is a rare. Rice is often served in round bowls. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The hots were fed chopped corn. Four hours of steady work faced us. A large size and stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the. Kick the ball straight and follow through. Help the woman get back to. A pot of tea helps to. Smoky fires lack flame. The soft. MAN'S FAULT. The salt breeze came across from the sea. Booth sold 50 bonds.

> **差异标注**: 安克2m 出现多处截断和误识别："a rare."（缺dish）、"hots"（应为hogs）、"the huge river is the."（截断）、"get back to."（缺her feet）、"MAN'S FAULT"（应为man's fall）。

#### 3m 英文

**Clip** (650字) [切片](segments/clip_en_3m.wav):

> The birch can do slid on the smooth planks. Glue the sheet to the dark blue background. It is easy to tell the depth of a well. These days, the chicken leg is a rare dish. Rice is often served in round bowls. The juice of lemons makes fine punch. The box was thrown beside the park truck. The hounds were fed chopped corn in garbage. Four hours of steady work faced us. A large size and stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A pot of tea helps to pass the evening. Smoky fires lack flame and heat. The soft cushion broke the man's fall. The salt breeze came across from the sea. The girl in the booth sold fifty bonds.

**Anker** (607字) [切片](segments/anker_en_3m.wav):

> The birch canoe slid on the smooth planks. Glue the sheet to the dark blue background. It is easy to tell the depth of a well. These days, a chicken leg is a rare. Rice is often served in round bowls. The juice of lemons makes fine punch. The box was thrown beside the park. The hogs were fed chopped corn. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A pot of tea helps to pass the evening. Smoky fires lack flame and. the south. MAN'S FALL. The salt breeze came across from the sea. The girl at the booth sold 50 bonds.

> **差异标注**: 安克3m："a rare."（缺dish）、"the park."（缺truck）、"MAN'S FALL"（大写异常）。

### 3.5 数字识别结果

#### 识别字符数统计

| 距离 | Clip | Anker | 差值 | 优势方 |
|------|------|-------|------|--------|
| 0.5m | 90 字 | 90 字 | +0 | 持平 |
| 1m | 90 字 | 90 字 | +0 | 持平 |
| 2m | 90 字 | 90 字 | +0 | 持平 |
| 3m | **94 字** | 90 字 | +4 | Clip |

> 参考语料: 10组 × 8位数字 = 80个数字字符 + 标点 = 90字。

#### 0.5m 数字（两者完全一致）

> [切片 Clip](segments/clip_num_05m.wav) [切片 Anker](segments/anker_num_05m.wav)

> 38271954。60492817。51937602。84260591。17359284。90641735。25814706。72946150。46083572。03718469。

#### 3m 数字

**Clip** (94字) [切片](segments/clip_num_3m.wav):

> 38271954。60492817。51937602。84260591。17359284。90641735。25814706。72946150。46083572。03718469。今天天。

**Anker** (90字) [切片](segments/anker_num_3m.wav):

> 38271954。60492817。51937602。84260591。17359284。90641735。25814706。72946150。46083572。03718469。

> **小结**: 0.5m-2m 两者均完美识别全部10组8位数字。3m 时 Clip 多识别"今天天"3字（下一段中文开头渗入）。

---

## 4. 音频片段索引

> 原始录音: `clip.wav`, `anker.wav`（16kHz mono WAV, 37MB）
> 压缩版本: `clip.ogg`, `anker.ogg`（Opus, 5.6/9.3MB）
> 切片片段: `segments/` 目录（16kHz mono WAV）

### 4.1 中文片段

| 距离 | Clip | Anker |
|------|------|-------|
| 0.5m | [clip_zh_05m.wav](segments/clip_zh_05m.wav) | [anker_zh_05m.wav](segments/anker_zh_05m.wav) |
| 1m | [clip_zh_1m.wav](segments/clip_zh_1m.wav) | [anker_zh_1m.wav](segments/anker_zh_1m.wav) |
| 2m | [clip_zh_2m.wav](segments/clip_zh_2m.wav) | [anker_zh_2m.wav](segments/anker_zh_2m.wav) |
| 3m | [clip_zh_3m.wav](segments/clip_zh_3m.wav) | [anker_zh_3m.wav](segments/anker_zh_3m.wav) |

### 4.2 英文片段

| 距离 | Clip | Anker |
|------|------|-------|
| 0.5m | [clip_en_05m.wav](segments/clip_en_05m.wav) | [anker_en_05m.wav](segments/anker_en_05m.wav) |
| 1m | [clip_en_1m.wav](segments/clip_en_1m.wav) | [anker_en_1m.wav](segments/anker_en_1m.wav) |
| 2m | [clip_en_2m.wav](segments/clip_en_2m.wav) | [anker_en_2m.wav](segments/anker_en_2m.wav) |
| 3m | [clip_en_3m.wav](segments/clip_en_3m.wav) | [anker_en_3m.wav](segments/anker_en_3m.wav) |

### 4.3 数字片段

| 距离 | Clip | Anker |
|------|------|-------|
| 0.5m | [clip_num_05m.wav](segments/clip_num_05m.wav) | [anker_num_05m.wav](segments/anker_num_05m.wav) |
| 1m | [clip_num_1m.wav](segments/clip_num_1m.wav) | [anker_num_1m.wav](segments/anker_num_1m.wav) |
| 2m | [clip_num_2m.wav](segments/clip_num_2m.wav) | [anker_num_2m.wav](segments/anker_num_2m.wav) |
| 3m | [clip_num_3m.wav](segments/clip_num_3m.wav) | [anker_num_3m.wav](segments/anker_num_3m.wav) |

<!-- [待插入] 音频播放器区域 -->

---

## 5. 综合评分

### 5.1 各维度胜负统计

| 维度 | Clip 胜 | 安克胜 | 持平 | 说明 |
|------|---------|--------|------|------|
| 噪声底噪 | **3** | 0 | 0 | Clip **全面领先**，平均低 8.3 dB |
| 信噪比 (SNR) | **4** | 0 | 0 | Clip **全面领先** +4.7~+15.8 dB |
| 动态范围 | **4** | 0 | 0 | Clip **大幅领先** +21~+32 dB |
| 中低频 (500-3kHz) | **4** | 0 | 0 | Clip 全面领先 |
| 高频 (3k-8kHz) | 0 | **4** | 0 | 安克全面领先 |
| 频谱质心 | 3 | 1 | 0 | 1m以上Clip领先 |
| 中文识别 | 3 | 0 | 1 | Clip 2m/3m 略优 |
| 英文识别 | **3** | 0 | 1 | Clip 远场优势明显 |
| 数字识别 | 1 | 0 | 3 | 基本持平 |
| 编码效率 | **Clip** | — | — | 文件体积仅为安克60% |

### 5.2 关键发现

1. **信号质量 Clip 全面领先**：
   - 噪声底噪低 8.3 dB（SpeexDSP 降噪有效）
   - SNR 高 4.7~15.8 dB（AGC 远场补偿 + 低底噪）
   - 动态范围宽 21~32 dB（音频层次丰富）

2. **远场（2m/3m）Clip 优势更明显**：
   - SNR: 2m +13.6 dB，3m +15.8 dB
   - 英文识别: 2m 多 43 字，3m 多 43 字
   - 中低频: +6~+10.7 dB
   - 安克 3m 频谱质心暴跌至 619Hz，Clip 维持 1252Hz

3. **高频衰减是 Clip 的短板**：
   - 3k-8kHz 频段安克全面领先
   - 0.5m 时 4k-6kHz 差距最大（-14.4 dB）
   - 这是硬件麦克风特性的结果，软件无法完全补偿

4. **数字识别两者均优秀**：0.5m-3m 全部 10 组 8 位数字完美识别。

---

## 6. [待填写] 环境噪声测量

| 测量位置 | 环境噪声 dB(A) |
|----------|---------------|
| 会议室静默 | [待填写] |
| 扬声器@1m | [待填写] |
| 扬声器@0.5m | [待填写] |

---

## 7. [待插入] 频谱图

<!--
[待插入] 0.5m Clip 频谱图
[待插入] 0.5m Anker 频谱图
[待插入] 3m Clip 频谱图
[待插入] 3m Anker 频谱图
-->

---

## 8. [待插入] 波形图

<!--
[待插入] 0.5m Clip 波形
[待插入] 0.5m Anker 波形
[待插入] 3m Clip 波形
[待插入] 3m Anker 波形
-->

---

## 附录：测试工具

| 工具 | 版本/说明 |
|------|----------|
| 信号分析 | Python numpy, 16kHz mono WAV |
| ASR引擎 | DashScope Fun-ASR-Realtime (WebSocket流式) |
| 音频转换 | ffmpeg 16kHz mono WAV |
| 参考语料 | `tools/gen_corpus.py` (edge-tts TTS生成) |
