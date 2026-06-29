# Cullary Desktop Packaging Plan

本文档规划 Cullary 从当前开发机可运行状态，推进到其他用户可安装、双击运行的 macOS App 的打包路线。

当前推荐路线：

```text
Tauri App
  + bundled Python runtime
  + bundled Python source
  + bundled minimal model set
  + bundled exiftool
  + runtime config
```

第一版不优先使用 PyInstaller。原因是当前 Python pipeline 仍在快速迭代，直接打包源码更容易调试、定位 traceback，也更接近现在的运行方式。后续 pipeline 稳定后，可以再评估 PyInstaller one-folder sidecar。

## Current State

当前 Rust 启动 pipeline 仍然依赖开发机假设：

```text
repo root: CULLARY_REPO_ROOT 或编译期 src-tauri/..
python: /opt/anaconda3/envs/hippo/bin/python 或 python3
PYTHONPATH: <repo>/src
model dir: ~/.cullary/models 或 CULLARY_MODEL_DIR
exiftool: PATH 中查找
```

这对开发机可用，但不能作为给其他用户的分发方式。生产包必须移除这些假设。

## Target App Layout

目标 macOS App bundle：

```text
Cullary.app/
  Contents/
    MacOS/
      Cullary
    Resources/
      runtime.json
      python/
        bin/python
        lib/...
        site-packages/...
      python-src/
        cullary/
      config/
        preprocess.default.json
      bin/
        exiftool
      models/
        yunet/
        mediapipe/
        hf-direct/
          facebook__dinov2-small/
          openai__clip-vit-base-patch32/
        laion-aesthetic/
```

Rust 启动 pipeline 时使用：

```text
Resources/python/bin/python
  -m cullary.pipeline
  /path/to/folder
  --progress jsonl
```

环境变量：

```text
PYTHONPATH=Resources/python-src
CULLARY_MODEL_DIR=Resources/models
CULLARY_EXIFTOOL=Resources/bin/exiftool
```

## Runtime Config

新增运行时配置，避免把路径写死在 Rust 代码中。

默认配置放在 App bundle 内：

```text
Cullary.app/Contents/Resources/runtime.json
```

用户/开发者覆盖配置：

```text
~/Library/Application Support/Cullary/runtime.local.json
```

开发模式示例：

```json
{
  "schema_version": "1.0",
  "pipeline_mode": "python_module",
  "python_binary": "/opt/anaconda3/envs/hippo/bin/python",
  "pythonpath": "/Users/liubin/Projects/Cullary/src",
  "working_dir": "/Users/liubin/Projects/Cullary",
  "module": "cullary.pipeline",
  "model_dir": "~/.cullary/models",
  "exiftool_binary": "/usr/local/bin/exiftool"
}
```

打包模式示例：

```json
{
  "schema_version": "1.0",
  "pipeline_mode": "python_module",
  "python_binary": "resources/python/bin/python",
  "pythonpath": "resources/python-src",
  "working_dir": "resources",
  "module": "cullary.pipeline",
  "model_dir": "resources/models",
  "exiftool_binary": "resources/bin/exiftool"
}
```

路径解析规则：

```text
absolute path          -> 原样使用
~                      -> expand 到用户 home
resources/...          -> App resource_dir 下相对路径
其他相对路径            -> 相对 runtime.json 所在目录
```

配置加载优先级：

```text
1. CULLARY_RUNTIME_CONFIG 指向的文件
2. ~/Library/Application Support/Cullary/runtime.local.json
3. App Resources/runtime.json
4. dev fallback: 当前 repo 逻辑
```

## Minimal Model Set

当前默认配置只需要打包最小模型集：

```text
models/yunet/face_detection_yunet_2023mar.onnx
models/mediapipe/selfie_segmenter.tflite
models/hf-direct/facebook__dinov2-small/
models/hf-direct/openai__clip-vit-base-patch32/
models/laion-aesthetic/sa_0_4_vit_b_32_linear.pth
```

当前默认不需要打包：

```text
models/hf-direct/facebook__dinov2-base/
models/hf-direct/google__siglip-base-patch16-224/
models/hf-direct/openai__clip-vit-large-patch14/
models/laion-aesthetic/sa_0_4_vit_l_14_linear.pth
```

这些可以作为未来高级模型包或可选下载，不进入第一版 bundle。

建议新增模型 manifest：

```text
packaging/models.manifest.json
```

用途：

- 明确要复制哪些模型文件；
- 构建前校验文件存在；
- 记录模型版本和 SHA256；
- 避免把实验模型误打进 App。

## Implementation Phases

### Phase 1: Runtime Config Layer

Status: implemented in code as the first packaging step.

目标：先不真正打包 Python runtime，只把启动逻辑配置化。

代码改动：

- Rust 增加 `RuntimeConfig` 结构。
- Rust 增加 `load_runtime_config(app)`。
- `start_pipeline` 从 config 读取：
  - `python_binary`
  - `pythonpath`
  - `working_dir`
  - `module`
  - `config_path`
  - `model_dir`
  - `exiftool_binary`
- Rust 启动子进程时设置：
  - `PYTHONPATH`
  - `CULLARY_MODEL_DIR`
  - `CULLARY_EXIFTOOL`
  - GUI-safe `PATH`
- Python `ensure_tools()` 支持：
  - 优先 `CULLARY_EXIFTOOL`
  - fallback `shutil.which("exiftool")`

当前已新增：

```text
packaging/runtime.dev.example.json
packaging/runtime.bundle.example.json
packaging/models.manifest.json
```

开发 fallback 会在首次启动 pipeline 时自动生成：

```text
build/runtime.dev.json
```

验收：

```bash
npm run check:desktop
npm run tauri:build -- --debug --no-bundle
```

并用开发配置启动真实 pipeline：

```text
runtime.local.json -> 当前 conda python + 当前 repo src + ~/.cullary/models
```

### Phase 2: Packaging Staging Directory

Status: implemented for source/config/exiftool/minimal-model staging, plus local smoke staging with a copied Python runtime.

目标：生成一个可检查的打包 staging 目录，但先不放进 `.app`。

新增脚本：

```text
scripts/package_runtime.py
```

生成：

```text
build/cullary-runtime/
  runtime.json
  python-src/
  config/
  bin/exiftool
  models/
```

第一版可以先不复制完整 Python runtime，只复制：

- `src/cullary`
- `config/preprocess.default.json`
- 最小模型集
- exiftool

当前命令：

```bash
python3 scripts/package_runtime.py
```

输出：

```text
build/cullary-runtime/
```

验收：

```bash
build/cullary-runtime/bin/python -m cullary.pipeline /path/to/test --progress jsonl
```

如果还未复制 Python runtime，则用开发机 Python 指向 staging 的 `python-src` 和 `models` 做验证。

### Phase 3: Bundled Python Runtime

Status: implemented for local smoke testing via direct environment copy. Release-grade runtime slimming/codesign/notarization is still pending.

目标：把 Python runtime 和 site-packages 复制到 staging。

候选方式：

```text
conda-pack
python-build-standalone + pip install
uv venv + copied venv
```

建议优先评估：

```text
conda-pack 当前 hippo env
```

原因：最接近当前已验证环境，风险较低。

Current implementation:

```bash
python3 scripts/package_runtime.py \
  --output build/cullary-runtime-with-python \
  --python-env /opt/anaconda3/envs/hippo
```

This copies the existing Python environment directly into:

```text
build/cullary-runtime-with-python/python
```

This is useful for local smoke testing the future App resource layout, but it is not yet the final release packaging method.

Observed size:

```text
build/cullary-runtime-with-python        ~2.8G
build/cullary-runtime-with-python/python ~2.1G
build/cullary-runtime-with-python/models ~665M
```

Observed runtime issue:

- importing `mediapipe` may initialize matplotlib/fontconfig caches.
- Rust now sets writable cache env vars when launching Python:
  - `MPLCONFIGDIR`
  - `XDG_CACHE_HOME`
  - `HF_HOME`
  - `TRANSFORMERS_OFFLINE=1`

需要注意：

- macOS native dylib 路径；
- torch / mediapipe / opencv / transformers 依赖；
- arm64/x64 架构一致性；
- 体积；
- codesign 递归签名。

验收：

```bash
build/cullary-runtime/python/bin/python -m cullary.pipeline /Users/liubin/Desktop/TestImage --progress jsonl
```

并确认：

```text
不依赖 /opt/anaconda3/envs/hippo/bin/python
不依赖 CULLARY_REPO_ROOT
不依赖 ~/.cullary/models
不依赖系统 PATH 中的 exiftool
```

### Phase 4: Tauri Resource Bundle

Status: implemented for a debug verification app using direct-copied Python environment resources.

目标：把 staging runtime 放进 Tauri bundle。

修改：

```text
src-tauri/tauri.conf.json
```

Current implementation keeps the normal app build lightweight and adds a separate runtime-bundle config:

```text
src-tauri/tauri.bundle-runtime.conf.json
```

Build and verification command:

```bash
npm run runtime:verify
```

Equivalent individual commands:

```bash
npm run runtime:stage
npm run runtime:build:app
npm run runtime:smoke
npm run runtime:smoke:full
```

Output:

```text
src-tauri/target/debug/bundle/macos/Cullary Runtime.app
```

Internal release DMG:

```bash
npm run runtime:verify:release
```

Outputs:

```text
src-tauri/target/release/bundle/macos/Cullary Runtime.app
src-tauri/target/release/bundle/dmg/Cullary_0.1.0_aarch64.dmg
```

The internal DMG uses a plain `create-dmg` mode with Finder prettifying skipped. This avoids the current Tauri DMG script failure in the agent environment while still producing a mountable internal test DMG. It is not signed or notarized.

DMG mount smoke verification:

```bash
npm run runtime:smoke:dmg
```

Verified result:

```text
/Volumes/Cullary/
  Applications -> /Applications
  Cullary Runtime.app

smoke_returncode: 0
```

Full release verification status:

```bash
npm run runtime:verify:release
```

Current result: passed on 2026-06-29.

Release summary artifact:

```text
src-tauri/target/release/bundle/Cullary Runtime.release-summary.json
```

The summary includes app size, DMG size, DMG SHA-256, target architecture, unsigned/internal channel, and verification status.

Internal tester instructions:

```text
wiki/internal_test_guide.md
```

Observed resource size:

```text
Cullary Runtime.app/Contents/Resources        ~2.9G
Resources/python                              ~2.2G
Resources/models                              ~665M
```

Resource smoke verification passed:

```text
Resources/python/bin/python -V
PYTHONPATH=Resources/python-src
CULLARY_MODEL_DIR=Resources/models
CULLARY_EXIFTOOL=Resources/bin/exiftool
import torch, transformers, mediapipe, cv2, cullary
```

Pipeline smoke from the generated `.app` passed using existing `.cullary` artifacts:

```bash
python3 scripts/smoke_app_runtime.py \
  --app "src-tauri/target/debug/bundle/macos/Cullary Runtime.app" \
  --folder /Users/liubin/Desktop/TestImage
```

This runs:

```text
Resources/python/bin/python -m cullary.pipeline <folder> --skip-preprocess --progress jsonl
```

with `PYTHONPATH`, `CULLARY_MODEL_DIR`, and `CULLARY_EXIFTOOL` pointing to App Resources.

Small full-pipeline smoke also passed against a 4-photo temp folder:

```bash
npm run runtime:smoke:full
```

This verifies the bundled Python runtime, bundled model whitelist, and bundled exiftool path without relying on the repo Python process.

For final release, the same resources should be reduced and then attached to the normal product build.

Future release config will add resources similar to:

```json
{
  "bundle": {
    "resources": [
      "../build/cullary-runtime/runtime.json",
      "../build/cullary-runtime/python",
      "../build/cullary-runtime/python-src",
      "../build/cullary-runtime/config",
      "../build/cullary-runtime/bin",
      "../build/cullary-runtime/models"
    ]
  }
}
```

具体路径需要按 Tauri 2 的 resource 复制规则验证。

验收：

```bash
npm run tauri:build
```

然后双击：

```text
src-tauri/target/release/bundle/macos/Cullary.app
```

验证：

- 不设置 `CULLARY_REPO_ROOT`；
- 不使用 `/opt/anaconda3/envs/hippo/bin/python`；
- 临时移走 `~/.cullary/models` 仍能跑；
- 临时移走系统 `exiftool` 或清空 PATH 仍能跑。

### Phase 5: Diagnostics

Status: Rust command implemented; UI display can be added when needed.

目标：用户机器上出错时给出可理解诊断，而不是 Python traceback。

Implemented command:

```text
get_runtime_diagnostics
```

The start screen now exposes this through a compact `运行环境检查` panel for internal testers.

It returns:

- runtime config source path and base dir;
- resolved Python, PYTHONPATH, working dir, config, model dir, exiftool, and cache paths;
- exists / is_file / is_dir status for each path;
- `python -V` and `exiftool -ver` results;
- env preview for `PYTHONPATH`, `CULLARY_MODEL_DIR`, `CULLARY_EXIFTOOL`, and `TRANSFORMERS_OFFLINE`.

Rust 增加 command：

```text
get_runtime_diagnostics()
```

检查：

- runtime config 来源；
- python binary exists；
- python `--version`；
- module import；
- model dir exists；
- required model files exist；
- exiftool exists；
- exiftool `-ver`；
- writable temp/cache check。

UI：

- 启动失败时展示诊断摘要；
- 提供“复制诊断信息”。

### Phase 6: Release Packaging

目标：生成可分发 DMG。

任务：

- release build；
- codesign；
- notarize；
- staple；
- DMG 安装测试。

验收环境：

```text
干净 macOS 用户账户
无 conda
无 repo
无 ~/.cullary/models
无 Homebrew exiftool
```

验收动作：

```text
1. 双击安装 DMG
2. 打开 Cullary.app
3. 选择测试图片目录
4. 运行 pipeline
5. 进入 Review
6. 标记保留/待删除
7. 全局最终确认
8. 验证 .to_delete 文件移动
```

## Code Change Checklist

Rust:

- [ ] `RuntimeConfig` struct
- [ ] resource path resolver
- [ ] user config path resolver
- [ ] `start_pipeline` 使用 runtime config
- [ ] `CULLARY_MODEL_DIR` 注入
- [ ] `CULLARY_EXIFTOOL` 注入
- [x] diagnostics command

Python:

- [ ] `ensure_tools()` 支持 `CULLARY_EXIFTOOL`
- [x] diagnostics 返回实际 `model_dir`
- [x] diagnostics 返回实际 `exiftool` 路径
- [ ] 可选：模型文件校验命令

Build scripts:

- [x] `packaging/models.manifest.json`
- [x] `scripts/package_runtime.py`
- [ ] staging 目录生成
- [ ] 最小模型集复制
- [x] exiftool 复制
- [x] Python runtime 复制 for local smoke staging
- [x] staging smoke test

Tauri:

- [x] bundle resources
- [ ] release build 验证
- [ ] DMG 验证

Docs:

- [ ] README 增加开发模式和打包模式说明
- [ ] integration contract 增加 runtime config 入口说明
- [ ] release checklist

## Open Decisions

仍需最终确认：

1. Python runtime 来源：`conda-pack`、`python-build-standalone` 还是复制 venv。
2. 是否只发布 arm64 macOS，还是同时支持 x64。
3. 模型是否全部内置，还是未来支持 optional model pack。
4. 是否第一版就做 codesign/notarize，还是先做内部 unsigned DMG。

建议：

```text
第一版只做 arm64 内测包。
先用 conda-pack。
只打包最小模型集。
先支持 unsigned/internal DMG，确认 runtime 稳定后再做 notarization。
```

## Success Criteria

完成打包工作的标准不是 `npm run tauri:build` 成功，而是：

```text
在一台没有 Cullary repo、没有 conda、没有 ~/.cullary/models、没有系统 exiftool 的 macOS 机器上，
用户安装 DMG 后双击 App，可以完成一次真实图片目录的 pipeline + review + staging。
```
