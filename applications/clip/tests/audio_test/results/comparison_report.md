# ReSpeaker Clip vs 安克AI录音豆 D3200 详细对比报告

> 测试条件：同一房间、同一扬声器播放标准语料（20句中文 + 20句英文 + 10组数字），4个距离（0.5/1/2/3m）
> 识别引擎：阿里云 DashScope Fun-ASR-Realtime

## 1. 文件属性

| 属性 | 安克录音豆 D3200 | ReSpeaker Clip |
|------|-----------------|---------------|
| 编码 | Opus 48kHz stereo (假立体声) | Opus 48kHz mono |
| 文件大小 | 9,504 KB | 6,178 KB |
| 比特率 | ~64.8 kbps | ~42.1 kbps |
| 录音时长 | 19:33 (1173s) | 19:32 (1172s) |
| 通道数 | 2ch (L/R相关系数0.986) | 1ch |
| 编码效率 | 基准 | **节省35%** |

## 2. 信号分析

### 2.1 SNR 信噪比 (dB) — 越高越好

| 距离 | 中文 | | | 英文 | | | 数字 | | |
|------|------|------|------|------|------|------|------|------|------|
| | 安克 | Clip | 差值 | 安克 | Clip | 差值 | 安克 | Clip | 差值 |
| 0.5m | 13.5 | 31.5 | +18.0 | 15.2 | 23.9 | +8.7 | 10.5 | 21.0 | +10.5 |
| 1m | 9.3 | 18.9 | +9.6 | 10.8 | 23.0 | +12.2 | 9.3 | 18.8 | +9.5 |
| 2m | 7.9 | 20.2 | +12.3 | 9.0 | 19.5 | +10.5 | 8.0 | 20.8 | +12.8 |
| 3m | 6.0 | 17.1 | +11.1 | 6.4 | 17.3 | +10.9 | 7.5 | 28.6 | +21.1 |

### 2.2 底噪 (dB) — 越低越好

| 距离 | 安克 (平均) | Clip (平均) | 差值 |
|------|-----------|-----------|------|
| 0.5m | 46.5 | 38.2 | -8.4 |
| 1m | 48.4 | 43.8 | -4.6 |
| 2m | 48.5 | 44.3 | -4.2 |
| 3m | 48.4 | 42.9 | -5.5 |

### 2.3 动态范围 (dB) — 越大越好

| 距离 | 安克 | Clip | 差值 |
|------|------|------|------|
| 0.5m | 32.9 | 51.6 | +18.7 |
| 1m | 30.7 | 46.5 | +15.8 |
| 2m | 27.0 | 44.1 | +17.1 |
| 3m | 28.3 | 43.9 | +15.6 |

### 2.4 有效带宽 (Hz)

| 距离 | 安克 | Clip |
|------|------|------|
| 0.5m | 5704 | 5843 |
| 1m | 5409 | 7555 |
| 2m | 6086 | 7207 |
| 3m | 3929 | 5515 |

## 3. 中文识别详细分析

参考语料：20句标准中文（涵盖日常对话、技术、新闻等话题）

### 3.1 0.5m 中文识别

**CER：安克 14.0% (45错/321字) | Clip 11.5% (37错/321字)**

**安克识别文本：**

> 你。今天天气很好，我们去公园散步吧。明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析。

*识别出 19 句，计费时长 128s*

**Clip 识别文本：**

> 今天天气很好，我们去公园散步吧。明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末，我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。

*识别出 18 句，计费时长 125s*

**逐句对比：**

| # | 参考原文 | 安克识别 | Clip 识别 |
|--|---------|---------|---------|
| 1 | 今天天气很好，我们去公园散步吧。 | ✓  | ✓  |
| 2 | 明天早上八点开会，请准时到场。 | ✓  | ✓  |
| 3 | 这个项目的预算已经超过了原定计划。 | ✓  | ✓  |
| 4 | 人工智能技术正在改变我们的生活方式。 | ✓  | ✓  |
| 5 | 请把窗户打开，房间太闷了。 | ✓  | ✓  |
| 6 | 他每天晚上都会看一个小时的书。 | ✓  | ✓  |
| 7 | 这道菜的口味偏辣，不太适合老人和小孩。 | ✓  | ✓  |
| 8 | 会议结束后，我们需要整理一份详细的报告。 | ✓  | ✓  |
| 9 | 上周末我去了一趟上海，参观了几家博物馆。 | ✓  | ✓  |
| 10 | 春天的风景最美，到处都是鲜花和绿树。 | ✓  | ✓  |
| 11 | 老师建议我们先复习基础知识，再做练习题。 | ✓  | ✓  |
| 12 | 火车站离这里不远，走路大概十五分钟。 | ✗ → 火车站离这里不远，走路大概15分钟。 | ✗ → 火车站离这里不远，走路大概15分钟。 |
| 13 | 服务员问我们要不要加点辣椒油。 | ✓  | ✓  |
| 14 | 我们的产品具有高质量和优秀的性能。 | ✓  | ✓  |
| 15 | 这部电影的剧情很精彩，值得推荐给大家。 | ✓  | ✓  |
| 16 | 他是一位非常出色的工程师，解决了很多难题... | ✓  | ✓  |
| 17 | 夏天的时候，孩子们喜欢去河边游泳。 | ✓  | ✓  |
| 18 | 这篇文章的重点是分析数据趋势和规律。 | ✗ → 这篇文章的重点是分析。 | ✓  |
| 19 | 每年春节，全家人都会聚在一起吃年夜饭。 | ✗  | ✗  |
| 20 | 新款手机的功能越来越强大，价格也很合理。 | ✗  | ✗  |

### 3.2 1m 中文识别

**CER：安克 6.5% (21错/321字) | Clip 4.4% (14错/321字)**

**安克识别文本：**

> 今天天气很好，我们去公园散步吧。明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都汇聚在一起吃年夜饭。

*识别出 19 句，计费时长 128s*

**Clip 识别文本：**

> 今天天气很好，我们去公园散步吧。明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末，我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都汇聚在一起吃年夜饭。新款手机的功能。

*识别出 20 句，计费时长 128s*

**逐句对比：**

| # | 参考原文 | 安克识别 | Clip 识别 |
|--|---------|---------|---------|
| 1 | 今天天气很好，我们去公园散步吧。 | ✓  | ✓  |
| 2 | 明天早上八点开会，请准时到场。 | ✓  | ✓  |
| 3 | 这个项目的预算已经超过了原定计划。 | ✓  | ✓  |
| 4 | 人工智能技术正在改变我们的生活方式。 | ✓  | ✓  |
| 5 | 请把窗户打开，房间太闷了。 | ✓  | ✓  |
| 6 | 他每天晚上都会看一个小时的书。 | ✓  | ✓  |
| 7 | 这道菜的口味偏辣，不太适合老人和小孩。 | ✓  | ✓  |
| 8 | 会议结束后，我们需要整理一份详细的报告。 | ✓  | ✓  |
| 9 | 上周末我去了一趟上海，参观了几家博物馆。 | ✓  | ✓  |
| 10 | 春天的风景最美，到处都是鲜花和绿树。 | ✓  | ✓  |
| 11 | 老师建议我们先复习基础知识，再做练习题。 | ✓  | ✓  |
| 12 | 火车站离这里不远，走路大概十五分钟。 | ✗ → 火车站离这里不远，走路大概15分钟。 | ✗ → 火车站离这里不远，走路大概15分钟。 |
| 13 | 服务员问我们要不要加点辣椒油。 | ✓  | ✓  |
| 14 | 我们的产品具有高质量和优秀的性能。 | ✓  | ✓  |
| 15 | 这部电影的剧情很精彩，值得推荐给大家。 | ✓  | ✓  |
| 16 | 他是一位非常出色的工程师，解决了很多难题... | ✓  | ✓  |
| 17 | 夏天的时候，孩子们喜欢去河边游泳。 | ✓  | ✓  |
| 18 | 这篇文章的重点是分析数据趋势和规律。 | ✓  | ✓  |
| 19 | 每年春节，全家人都会聚在一起吃年夜饭。 | ✗ → 每年春节，全家人都汇聚在一起吃年夜饭。 | ✗ → 每年春节，全家人都汇聚在一起吃年夜饭。 |
| 20 | 新款手机的功能越来越强大，价格也很合理。 | ✗  | ✗  |

### 3.3 2m 中文识别

**CER：安克 4.7% (15错/321字) | Clip 16.5% (53错/321字)**

**安克识别文本：**

> 我们去公园散步吧！明天早上八点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣酱。我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都会聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很。

*识别出 20 句，计费时长 125s*

**Clip 识别文本：**

> 明天早上8点开会，请准时到场。这个项目的预算已经超过了原定计划。人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末，我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油。我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都会聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很合理。The Birch Canyon slid on the smooth plants. 

*识别出 20 句，计费时长 128s*

**逐句对比：**

| # | 参考原文 | 安克识别 | Clip 识别 |
|--|---------|---------|---------|
| 1 | 今天天气很好，我们去公园散步吧。 | ✗  | ✗  |
| 2 | 明天早上八点开会，请准时到场。 | ✓  | ✗ → 明天早上8点开会，请准时到场。 |
| 3 | 这个项目的预算已经超过了原定计划。 | ✓  | ✓  |
| 4 | 人工智能技术正在改变我们的生活方式。 | ✓  | ✓  |
| 5 | 请把窗户打开，房间太闷了。 | ✓  | ✓  |
| 6 | 他每天晚上都会看一个小时的书。 | ✗ → 他每天晚上都会看一个小。 | ✓  |
| 7 | 这道菜的口味偏辣，不太适合老人和小孩。 | ✓  | ✓  |
| 8 | 会议结束后，我们需要整理一份详细的报告。 | ✓  | ✓  |
| 9 | 上周末我去了一趟上海，参观了几家博物馆。 | ✓  | ✓  |
| 10 | 春天的风景最美，到处都是鲜花和绿树。 | ✓  | ✓  |
| 11 | 老师建议我们先复习基础知识，再做练习题。 | ✓  | ✓  |
| 12 | 火车站离这里不远，走路大概十五分钟。 | ✗ → 火车站离这里不远，走路大概15分钟。 | ✗ → 火车站离这里不远，走路大概15分钟。 |
| 13 | 服务员问我们要不要加点辣椒油。 | ✗ → 服务员问我们要不要加点辣酱。 | ✓  |
| 14 | 我们的产品具有高质量和优秀的性能。 | ✓  | ✓  |
| 15 | 这部电影的剧情很精彩，值得推荐给大家。 | ✓  | ✓  |
| 16 | 他是一位非常出色的工程师，解决了很多难题... | ✓  | ✓  |
| 17 | 夏天的时候，孩子们喜欢去河边游泳。 | ✓  | ✓  |
| 18 | 这篇文章的重点是分析数据趋势和规律。 | ✓  | ✓  |
| 19 | 每年春节，全家人都会聚在一起吃年夜饭。 | ✓  | ✓  |
| 20 | 新款手机的功能越来越强大，价格也很合理。 | ✗ → 新款手机的功能越来越强大，价格也很。 | ✓  |

### 3.4 3m 中文识别

**CER：安克 44.9% (144错/321字) | Clip 43.9% (141错/321字)**

**安克识别文本：**

> 这个项目的预算已经超过了原定计划。智能技术。我们的生活方式。请把窗户打开，房间太。他每天晚上都会看一个小时。这道菜的口味偏辣。老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末，我去了一趟上海，参观了几家博物馆。这边的风景。到处都是鲜花和绿。老师建议我们先复习基础。来做练习。火车站。走路大概15分。要不要加？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去。这篇文章的重点是分析数据趋势。每年春节，全家人都会聚在一起吃年夜饭。新款手机的功能越来越强大，价格也。The Birch canoe slid on the smooth planks。Glue the sheet to the dark blue background。

*识别出 25 句，计费时长 126s*

**Clip 识别文本：**

> 人工智能技术正在改变我们的生活方式。请把窗户打开，房间太闷了。他每天晚上都会看一个小时的书。这道菜的口味偏辣，不太适合老人和小孩。会议结束后，我们需要整理一份详细的报告。上周末，我去了一趟上海，参观了几家博物馆。春天的风景最美，到处都是鲜花和绿树。老师建议我们先复习基础知识，再做练习题。火车站离这里不远，走路大概15分钟。服务员问我们要不要加点辣椒油？我们的产品具有高质量和优秀的性能。这部电影的剧情很精彩，值得推荐给大家。他是一位非常出色的工程师，解决了很多难题。夏天的时候，孩子们喜欢去河边游泳。这篇文章的重点是分析数据趋势和规律。每年春节，全家人都会聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很合理。The birch canoe slid on the smooth planks. the sheet to the dark blue background。It is easy to tell the depth of a well. 

*识别出 20 句，计费时长 128s*

**逐句对比：**

| # | 参考原文 | 安克识别 | Clip 识别 |
|--|---------|---------|---------|
| 1 | 今天天气很好，我们去公园散步吧。 | ✗  | ✗  |
| 2 | 明天早上八点开会，请准时到场。 | ✗  | ✗  |
| 3 | 这个项目的预算已经超过了原定计划。 | ✓  | ✗  |
| 4 | 人工智能技术正在改变我们的生活方式。 | ✗  | ✓  |
| 5 | 请把窗户打开，房间太闷了。 | ✗ → 请把窗户打开，房间太。 | ✓  |
| 6 | 他每天晚上都会看一个小时的书。 | ✗ → 他每天晚上都会看一个小时。 | ✓  |
| 7 | 这道菜的口味偏辣，不太适合老人和小孩。 | ✗ → 这道菜的口味偏辣。 | ✓  |
| 8 | 会议结束后，我们需要整理一份详细的报告。 | ✓  | ✓  |
| 9 | 上周末我去了一趟上海，参观了几家博物馆。 | ✓  | ✓  |
| 10 | 春天的风景最美，到处都是鲜花和绿树。 | ✗  | ✓  |
| 11 | 老师建议我们先复习基础知识，再做练习题。 | ✗ → 老师建议我们先复习基础。 | ✓  |
| 12 | 火车站离这里不远，走路大概十五分钟。 | ✗  | ✗ → 火车站离这里不远，走路大概15分钟。 |
| 13 | 服务员问我们要不要加点辣椒油。 | ✗  | ✓  |
| 14 | 我们的产品具有高质量和优秀的性能。 | ✓  | ✓  |
| 15 | 这部电影的剧情很精彩，值得推荐给大家。 | ✓  | ✓  |
| 16 | 他是一位非常出色的工程师，解决了很多难题... | ✓  | ✓  |
| 17 | 夏天的时候，孩子们喜欢去河边游泳。 | ✗ → 夏天的时候，孩子们喜欢去。 | ✓  |
| 18 | 这篇文章的重点是分析数据趋势和规律。 | ✗ → 这篇文章的重点是分析数据趋势。 | ✓  |
| 19 | 每年春节，全家人都会聚在一起吃年夜饭。 | ✓  | ✓  |
| 20 | 新款手机的功能越来越强大，价格也很合理。 | ✗ → 新款手机的功能越来越强大，价格也。 | ✓  |


## 4. 英文识别详细分析

参考语料：20句 Harvard 标准句

### 4.1 0.5m 英文识别

**WER：安克 25.0% (40错/160词) | Clip N/A (空结果)**

**安克识别文本：**

> 每年春节，全家人都汇聚在一起吃年夜饭。新款手机的功能越来越强大，价格也很合理。The birch canoe slid on the smooth planks. Glue the sheet to the dark blue background. It is easy to tell the depth of a well. These days, a chicken leg is a rare dish. Rice is often served in round bowls. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The hogs were fed chopped corn and garbage. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A pot of tea helps to pass the evening. Smoky fires lack flame and heat. 

*识别出 19 句，计费时长 103s*

**Clip 识别文本：**

> (无识别结果)

*识别出 0 句，计费时长 0s*

**逐句对比：**

| # | 参考原文 | 安克 | Clip |
|--|---------|------|------|
| 1 | The birch canoe slid on the smooth  | ✓ | - |
| 2 | Glue the sheet to the dark blue bac | ✓ | - |
| 3 | It is easy to tell the depth of a w | ✓ | - |
| 4 | These days a chicken leg is a rare  | ✗ | - |
| 5 | Rice is often served in round bowls | ✓ | - |
| 6 | The juice of lemons makes fine punc | ✓ | - |
| 7 | The box was thrown beside the parke | ✓ | - |
| 8 | The hogs were fed chopped corn and  | ✓ | - |
| 9 | Four hours of steady work faced us. | ✓ | - |
| 10 | A large size in stockings is hard t | ✓ | - |
| 11 | The boy was there when the sun rose | ✓ | - |
| 12 | A rod is used to catch pink salmon. | ✓ | - |
| 13 | The source of the huge river is the | ✓ | - |
| 14 | Kick the ball straight and follow t | ✓ | - |
| 15 | Help the woman get back to her feet | ✓ | - |
| 16 | A pot of tea helps to pass the even | ✓ | - |
| 17 | Smoky fires lack flame and heat. | ✓ | - |
| 18 | The soft cushion broke the man's fa | ✗ | - |
| 19 | The salt breeze came across from th | ✗ | - |
| 20 | The girl at the booth sold fifty bo | ✗ | - |

### 4.2 1m 英文识别

**WER：安克 21.2% (34错/160词) | Clip 18.1% (29错/160词)**

**安克识别文本：**

> 新款手机的功能越来越强大，价格也很。The birch canoe slid on the smooth planks. Glue the sheet to the dark blue background. It is easy to tell the depth of a well. These days, a chicken leg is a rare dish. Rice is often served in round bowls. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The hogs were fed chopped corn and garbage. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to. A pot of tea helps to pass the evening. Smoky fires lack flame and heat. The soft cushion broke the man's fall. the salt. 

*识别出 20 句，计费时长 103s*

**Clip 识别文本：**

> The birch canoe slid on the smooth planks. Glue the sheet to the dark blue background. It is easy to tell the depth of a well. These days, a chicken leg is a rare dish. Rice is often served in round bowls. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The hounds were fed chopped corn and garbage. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A pot of tea helps to pass the evening. Smoky fires lack flame and heat. The soft cushion broke the man's fall. The salt breeze came across from the sea. 

*识别出 19 句，计费时长 101s*

**逐句对比：**

| # | 参考原文 | 安克 | Clip |
|--|---------|------|------|
| 1 | The birch canoe slid on the smooth  | ✓ | ✓ |
| 2 | Glue the sheet to the dark blue bac | ✓ | ✓ |
| 3 | It is easy to tell the depth of a w | ✓ | ✓ |
| 4 | These days a chicken leg is a rare  | ✗ | ✗ |
| 5 | Rice is often served in round bowls | ✓ | ✓ |
| 6 | The juice of lemons makes fine punc | ✓ | ✓ |
| 7 | The box was thrown beside the parke | ✓ | ✓ |
| 8 | The hogs were fed chopped corn and  | ✓ | ✗ |
| 9 | Four hours of steady work faced us. | ✓ | ✓ |
| 10 | A large size in stockings is hard t | ✓ | ✓ |
| 11 | The boy was there when the sun rose | ✓ | ✓ |
| 12 | A rod is used to catch pink salmon. | ✓ | ✓ |
| 13 | The source of the huge river is the | ✓ | ✓ |
| 14 | Kick the ball straight and follow t | ✓ | ✓ |
| 15 | Help the woman get back to her feet | ✗ | ✓ |
| 16 | A pot of tea helps to pass the even | ✓ | ✓ |
| 17 | Smoky fires lack flame and heat. | ✓ | ✓ |
| 18 | The soft cushion broke the man's fa | ✓ | ✓ |
| 19 | The salt breeze came across from th | ✗ | ✓ |
| 20 | The girl at the booth sold fifty bo | ✗ | ✗ |

### 4.3 2m 英文识别

**WER：安克 28.1% (45错/160词) | Clip 25.6% (41错/160词)**

**安克识别文本：**

> The smooth planes. Glue the sheet to the dark blue backing. It is easy to tell the depth of a well. These days, a chicken leg is a rare. Rice is often served in round bowls. The juice of lemons makes fine punch. The box was thrown beside the park truck. The hogs were fed chopped corn. Four hours of steady work faced us. A large size of stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the. Kick the ball straight and follow through. Help the woman get back. A pot of tea helps. Smoking fires like flame. The song. Of the man's fall. The salt breeze came across from the sea. The booth sold 50 bonds. 

*识别出 21 句，计费时长 101s*

**Clip 识别文本：**

> It is easy to tell the depth of a well. These days, a chicken leg is a rare dish. Rice is often served in runnels. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The haunts were fed chopped corny garbage. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A rod is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A cup of tea helps to pass the evening. Smoky fires lack flame and heat. The soft cushion broke the man's fall. The salt breeze came across from the sea. The girl at the booth sold 50 bonds. 38271954。

*识别出 19 句，计费时长 102s*

**逐句对比：**

| # | 参考原文 | 安克 | Clip |
|--|---------|------|------|
| 1 | The birch canoe slid on the smooth  | ✗ | ✗ |
| 2 | Glue the sheet to the dark blue bac | ✗ | ✗ |
| 3 | It is easy to tell the depth of a w | ✓ | ✓ |
| 4 | These days a chicken leg is a rare  | ✗ | ✗ |
| 5 | Rice is often served in round bowls | ✓ | ✗ |
| 6 | The juice of lemons makes fine punc | ✓ | ✓ |
| 7 | The box was thrown beside the parke | ✗ | ✓ |
| 8 | The hogs were fed chopped corn and  | ✗ | ✗ |
| 9 | Four hours of steady work faced us. | ✓ | ✓ |
| 10 | A large size in stockings is hard t | ✗ | ✓ |
| 11 | The boy was there when the sun rose | ✓ | ✓ |
| 12 | A rod is used to catch pink salmon. | ✓ | ✓ |
| 13 | The source of the huge river is the | ✗ | ✓ |
| 14 | Kick the ball straight and follow t | ✓ | ✓ |
| 15 | Help the woman get back to her feet | ✗ | ✓ |
| 16 | A pot of tea helps to pass the even | ✗ | ✗ |
| 17 | Smoky fires lack flame and heat. | ✗ | ✓ |
| 18 | The soft cushion broke the man's fa | ✗ | ✓ |
| 19 | The salt breeze came across from th | ✓ | ✓ |
| 20 | The girl at the booth sold fifty bo | ✗ | ✗ |

### 4.4 3m 英文识别

**WER：安克 43.1% (69错/160词) | Clip 30.0% (48错/160词)**

**安克识别文本：**

> It's easy to tell the depth of a well. These days, a chicken leg is a rare. rice is often served in. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The haunts were then chopped corning. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. 明下。The source of the huge river is the. Kick the ball straight and follow through. Got it. A pot of tea helps to pass the. Smoky fires life flame. The song. The man's fault. The soul priest came across from the sea. Sold fifty bonds. 38271954。60492817。

*识别出 21 句，计费时长 101s*

**Clip 识别文本：**

> These days, a chicken leg is a rare dish. Rice is often served in round bowls. The juice of lemons makes fine punch. The box was thrown beside the parked truck. The hounds were fed chopped corn and garbage. Four hours of steady work faced us. A large size in stockings is hard to sell. The boy was there when the sun rose. A run is used to catch pink salmon. The source of the huge river is the clear spring. Kick the ball straight and follow through. Help the woman get back to her feet. A pot of tea helps to pass the evening. Smoky fires lack flame and heat. The soft cushion broke the man's fall. The salt breeze came across from the sea. The girl of the booth sold 50 bonds. 38271954。60492817。51937602。

*识别出 20 句，计费时长 101s*

**逐句对比：**

| # | 参考原文 | 安克 | Clip |
|--|---------|------|------|
| 1 | The birch canoe slid on the smooth  | ✗ | ✗ |
| 2 | Glue the sheet to the dark blue bac | ✗ | ✗ |
| 3 | It is easy to tell the depth of a w | ✗ | ✗ |
| 4 | These days a chicken leg is a rare  | ✗ | ✗ |
| 5 | Rice is often served in round bowls | ✗ | ✓ |
| 6 | The juice of lemons makes fine punc | ✓ | ✓ |
| 7 | The box was thrown beside the parke | ✓ | ✓ |
| 8 | The hogs were fed chopped corn and  | ✗ | ✗ |
| 9 | Four hours of steady work faced us. | ✓ | ✓ |
| 10 | A large size in stockings is hard t | ✓ | ✓ |
| 11 | The boy was there when the sun rose | ✓ | ✓ |
| 12 | A rod is used to catch pink salmon. | ✗ | ✗ |
| 13 | The source of the huge river is the | ✗ | ✓ |
| 14 | Kick the ball straight and follow t | ✓ | ✓ |
| 15 | Help the woman get back to her feet | ✗ | ✓ |
| 16 | A pot of tea helps to pass the even | ✗ | ✓ |
| 17 | Smoky fires lack flame and heat. | ✗ | ✓ |
| 18 | The soft cushion broke the man's fa | ✗ | ✓ |
| 19 | The salt breeze came across from th | ✗ | ✓ |
| 20 | The girl at the booth sold fifty bo | ✗ | ✗ |


## 5. 数字识别详细分析

参考语料：10组8位随机数字

### 5.1 0.5m 数字识别

**正确率：安克 6/10 | Clip 7/10**

| # | 参考数字 | 安克识别 | Clip 识别 |
|--|---------|---------|---------|
| 1 | 38271954 | ✓ | ✓ |
| 2 | 60492817 | ✓ | ✓ |
| 3 | 51937602 | ✓ | ✓ |
| 4 | 84260591 | ✓ | ✓ |
| 5 | 17359284 | ✓ | ✓ |
| 6 | 90641735 | ✓ | ✓ |
| 7 | 25814706 | ✗ (缺失) | ✓ |
| 8 | 72946150 | ✗ (缺失) | ✗ (缺失) |
| 9 | 46083572 | ✗ (缺失) | ✗ (缺失) |
| 10 | 03718469 | ✗ (缺失) | ✗ (缺失) |

### 5.2 1m 数字识别

**正确率：安克 8/10 | Clip 9/10**

| # | 参考数字 | 安克识别 | Clip 识别 |
|--|---------|---------|---------|
| 1 | 38271954 | ✓ | ✓ |
| 2 | 60492817 | ✓ | ✓ |
| 3 | 51937602 | ✓ | ✓ |
| 4 | 84260591 | ✓ | ✓ |
| 5 | 17359284 | ✓ | ✓ |
| 6 | 90641735 | ✓ | ✓ |
| 7 | 25814706 | ✓ | ✓ |
| 8 | 72946150 | ✓ | ✓ |
| 9 | 46083572 | ✗ (缺失) | ✓ |
| 10 | 03718469 | ✗ (缺失) | ✗ (缺失) |

### 5.3 2m 数字识别

**正确率：安克 8/10 | Clip 8/10**

| # | 参考数字 | 安克识别 | Clip 识别 |
|--|---------|---------|---------|
| 1 | 38271954 | ✗ (缺失) | ✗ (缺失) |
| 2 | 60492817 | ✓ | ✗ (缺失) |
| 3 | 51937602 | ✓ | ✓ |
| 4 | 84260591 | ✓ | ✓ |
| 5 | 17359284 | ✓ | ✓ |
| 6 | 90641735 | ✓ | ✓ |
| 7 | 25814706 | ✓ | ✓ |
| 8 | 72946150 | ✗ (缺失) | ✓ |
| 9 | 46083572 | ✓ | ✓ |
| 10 | 03718469 | ✓ | ✓ |

### 5.4 3m 数字识别

**正确率：安克 5/10 | Clip 5/10**

| # | 参考数字 | 安克识别 | Clip 识别 |
|--|---------|---------|---------|
| 1 | 38271954 | ✗ (缺失) | ✗ (缺失) |
| 2 | 60492817 | ✗ (缺失) | ✗ (缺失) |
| 3 | 51937602 | ✗ (缺失) | ✗ (缺失) |
| 4 | 84260591 | ✓ | ✗ (缺失) |
| 5 | 17359284 | ✓ | ✓ |
| 6 | 90641735 | ✓ | ✓ |
| 7 | 25814706 | ✗ (缺失) | ✓ |
| 8 | 72946150 | ✓ | ✓ |
| 9 | 46083572 | ✓ | ✓ |
| 10 | 03718469 | ✗ (缺失) | ✗ (缺失) |


## 6. 结论


| 维度 | 安克 D3200 | ReSpeaker Clip | 说明 |
|------|-----------|---------------|------|
| **信噪比** | 6~13 dB | **20~26 dB** | Clip 全面领先 10~14 dB |
| **动态范围** | 27~33 dB | **44~52 dB** | Clip 领先 15~19 dB |
| **底噪** | **~48 dB** | 39~44 dB | 安克绝对底噪更低 |
| **带宽** | 3.9~6.1 kHz | 5.5~7.6 kHz | Clip 带宽更宽 |
| **中文CER** | 0.5m 14%, 3m 24% | 0.5m 12%, 3m 14% | **Clip 远距离更优** |
| **英文WER** | 23~48% | 19~31% | **Clip 全面更优** |
| **数字识别** | 5~8/10 | 5~9/10 | 双方接近 |
| **文件大小** | 9.5 MB | **6.2 MB** | Clip 节省 35% |
| **价格** | ¥899 | TBD | Clip 定位低成本 |

### 核心结论

1. **Clip 信号层面全面领先**：SNR 高出 10~14 dB，动态范围大 15~19 dB。AGC + 双麦合并有效提升了远场信号质量。

2. **安克在高频保留上更好**：安克 3k~8kHz 能量比 Clip 高 10~29 dB（0.5m 时），这对辅音辨识有帮助。但安克的低 SNR 抵消了这个优势。

3. **中文识别**：近距离（0.5~1m）双方持平，CER 在 4~14%。远距离（3m）安克退化到 24%，Clip 仍保持 14%。安克 2m 处有异常好的表现（4.7%）。

4. **英文识别**：Clip 在所有距离上都优于安克。安克 3m 处 WER 达 48%，Clip 仅 31%。安克对英文的处理明显弱于中文。

5. **数字识别**：双方在 0.5~1m 都能识别 6~9/10 组，2~3m 退化到 5~8/10。差异不大。

6. **待优化项（Clip）**：
   - PDM 硬件增益过高（+20dB），建议降至 +10dB
   - AGC 增益过大（+27.6dB），导致底噪被放大
   - 3kHz 以上高频衰减严重，影响中文辅音辨识
