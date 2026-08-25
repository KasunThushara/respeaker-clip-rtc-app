# Clip vs Anker D3200 对比测试流程

> 语料和测试标准参照本目录 `audio_quality_standard.md` Section 4 & 9

## 准备（5 min）

- [ ] 手机传输 `corpus/test_combined.wav`（19 min，包含 4 个距离段）
- [ ] Clip 满电，烧好固件
- [ ] 安克满电
- [ ] 卷尺

## Clip 模式切换（BLE 或 UDP Terminal）

```
AT+MODE=merge     → Enhanced（DSP + AGC）
AT+MODE=stereo    → Normal（无 DSP）
AT+RECORD         → 开始
AT+STOP           → 停止
```

---

## 测试步骤

> 播放 `test_combined.wav`（19 min），内含 4 段：0.5m / 1m / 2m / 3m
> 每段 ~4.7 min（zh + en + digits），段间 8s 静音用于移动设备
> **一次录音录完全部 4 个距离，中间不停**

### 静音房间（~40 min）

```
Round 1: Clip Enhanced + Anker 同时录（~19 min）
  1. 设备放 0.5m 处，开始录音
  2. 播放 test_combined.wav
  3. 播到第 1 段结束后（~4:43），8s 内移到 1m
  4. 播到第 2 段结束后（~9:31），8s 内移到 2m
  5. 播到第 3 段结束后（~14:19），8s 内移到 3m
  6. 播完后停止两台设备

Round 2: Clip Normal + Anker 同时录（~19 min）
  1. AT+MODE=stereo
  2. 重复上述步骤
```

### 会议室（~40 min）

```
同上，换个房间再来 Round 1 + Round 2
```

---

## 时间预估

| 项目 | 时间 |
|------|------|
| 准备 | 5 min |
| 静音房间 2 轮（各 ~19 min）| 40 min |
| 转场 | 5 min |
| 会议室 2 轮（各 ~19 min）| 40 min |
| 导出 | 10 min |
| **总计** | **~1.5 小时** |

---

## 文件命名

导出录音放到 `results/` 根目录：

```
results/
  quiet/
    clip_enhanced.ogg    ← 一段连续录音
    clip_normal.ogg
    anker.ogg
  meeting/
    clip_enhanced.ogg
    clip_normal.ogg
    anker.ogg
```

---

## 分析（录音完成后）

```bash
cd applications/clip/tests/audio_test

# Step 1: 自动按距离切分（根据 distances.json 时间戳）
python tools/audio_test_runner.py split

# Step 2: 基本参数对比
python tools/audio_test_runner.py analyze --report

# Step 3: 语音识别率（可选，需要 whisper）
python tools/audio_test_runner.py wer
```

切分后自动生成：
```
results/quiet/0.5m/clip_enhanced_zh.wav  clip_enhanced_en.wav  clip_enhanced_digits.wav
results/quiet/1m/   ...
results/quiet/2m/   ...
results/quiet/3m/   ...
```
