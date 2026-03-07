# Video Generation Pipeline Cost Breakdown Per Stitch

> Last updated: 2026-02-14

## x.ai Pricing (Relevant Models)

| Model | Input | Output | Unit |
|-------|-------|--------|------|
| **grok-3** | $3.00 | $15.00 | per 1M tokens |
| **grok-imagine-video** | $0.05/sec | | per second of generated video |
| **grok-imagine-image** | $0.02 | | per image |

Source: [x.ai Developer Docs](https://docs.x.ai/developers/models)

---

## Pipeline Overview

Each "stitch" is a full compilation video (~36 seconds) made of **6 AI-generated video clips** stitched together.

```
Grok-3 generates compilation structure + prompts
  └─ 6 clips with image prompts, video prompts, dialogue
            ↓
FOR EACH CLIP (×6):
  ├─ grok-imagine-image → generates a still frame ($0.02)
  ├─ grok-imagine-video → animates it into 6-sec clip ($0.30)
  ├─ Poll for completion (async, up to 10 min)
  ├─ Download video file
  └─ Trim to exactly 6 seconds (FFmpeg, local)
            ↓
Grok-3 generates TikTok caption
            ↓
FFmpeg stitches all 6 clips into final video (local, free)
            ↓
Output: ~36-second vertical video (9:16, 720p)
```

---

## Cost Breakdown

### 1. Grok-3 Script & Caption Generation (2 calls)

| Call | Input Tokens | Output Tokens |
|------|---|---|
| Compilation markdown (clip structure + prompts) | ~3,000 | ~4,000 |
| TikTok caption generation | ~1,500 | ~500 |
| **Total** | **~4,500** | **~4,500** |

**Grok-3 cost: ~$0.08**

- Input: ~4.5K / 1M × $3.00 = $0.014
- Output: ~4.5K / 1M × $15.00 = $0.068

### 2. grok-imagine-image Still Frame Generation (6 calls)

- 6 images × $0.02 each

**Image cost: $0.12**

### 3. grok-imagine-video Video Clip Generation (6 calls)

- 6 clips × 6 seconds each × $0.05/sec

**Video cost: $1.80**

### 4. FFmpeg Stitching Free (local)

---

## Total Cost Per Stitch

| Component | API Calls | Cost |
|-----------|-----------|------|
| Grok-3 (text) | 2 | $0.08 |
| grok-imagine-image | 6 | $0.12 |
| grok-imagine-video | 6 | **$1.80** |
| FFmpeg stitch | local | $0.00 |
| **Total** | **14** | **~$2.00** |

**One full stitch costs roughly $2.00.**

Video generation is by far the dominant cost at **90% of total spend**.

---

## Cost at Scale

| Videos | Total Cost |
|--------|-----------|
| 1 | ~$2.00 |
| 10 | ~$20.00 |
| 50 | ~$100.00 |
| 100 | ~$200.00 |

---

## Key Config

- **Clips per video**: 6 (configurable)
- **Clip duration**: 6 seconds each
- **Resolution**: 720p
- **Aspect ratio**: 9:16 (vertical / TikTok)
- **Rate limiting**: Adaptive cooldown (5–15s between calls)
- **Retry logic**: Built-in with exponential backoff
