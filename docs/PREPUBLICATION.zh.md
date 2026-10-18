# GitHub 源码上传前审查 — 0.4.5

此为 0.4.5 历史记录。0.4.6 安装包许可修正及重新测试以 [LICENSE-AUDIT.zh.md](LICENSE-AUDIT.zh.md) 为准。

日期：2026-10-17。结论：当前待收录源码未发现公开上传的阻断问题；安装包公开分发仍有下述许可事项待完成。
本轮没有提交、推送、创建远程仓库或 Release，没有操作摄像头、麦克风或外部 AI。

## 审查范围与结果

- Git 待收录的 99 个文件全部纳入检查，包括未跟踪文件；当前仓库没有提交历史或已跟踪文件。
- 独立只读代码审查未确认 Critical/P1/P2 缺陷。接口密钥绑定、禁止重定向、取消/超时、目标冻结、迟到结果丢弃与退出流程和测试相符。
- **193 项 pytest 通过，24.35 秒**，启用 `LOOK_TO_ASK_TEST_CUDA=1`；ruff check、format check、pip check 通过。
- 英文 README 的版本、操作、设置、隐私、限制及本地链接已核对；明确 GitHub 当前提供源码，本地安装包名称不是公开下载入口。
- Gitleaks 8.30.1 使用完整规则扫描 Git 候选文件副本，报告全量脱敏；未发现密钥泄漏。另核对用户绝对路径、私钥、媒体/校准文件与凭据 URL。
- 凭据 URL 唯一命中来自 `tests/test_vision.py` 的非法接口拒绝测试，是公开测试样例；没有使用真实凭据。
- 61 个锁定 PyPI 版本均可找到公开发布文件，固定 PyAV wheel 地址返回 HTTP 200。此项不等于在干净系统完成安装。
- EyeTrax 原始许可、上游版本/commit、11 个 vendored 文件哈希一致；Qt/FFmpeg 源码档案固定哈希检查通过。
- 实际本地 bundle 扫描通过：1452 个文件，约 693.1 MiB；未发现扫描规则覆盖的私人数据、退役实验或可选 NVIDIA DLL。

## 本轮修正

1. 源码 ZIP 曾多收录 5 个生成的 `.egg-info/*.txt`。过滤现已排除生成元数据、隐藏缓存及不同大小写的截图/录音/校准目录；真实 ZIP 回归夹具验证修正。
2. 增加 `build_windows.py --source-only`，只更新源码 ZIP 和校验和，保留已有二进制。
3. `.gitattributes` 固定文本为 LF，QM 为二进制，避免 Windows `core.autocrlf=true` 改变 vendored 哈希。
4. 实际 CTranslate2/tokenizers wheel 缺少许可文件，Python 运行时也不属于 pip 许可枚举范围。收集脚本已补齐固定版本/哈希的上游文本及实际 CPython 许可；真实收集与错误路径验证通过。

源码包已重新生成，最终候选清单、脱敏扫描、文件哈希和源码 ZIP 对照记录保留在本地
`.venv/preupload-audit-0.4.5/`，不进入 Git。

## 许可证结论与二进制边界

项目原创源码和收录的 EyeTrax 子集为 MIT，原版权和许可文本均保留。
运行依赖通过声明安装，未将其二进制或通用模型权重加入 Git；未发现阻碍当前 MIT 源码仓库公开的许可冲突。
依赖各自的许可不被项目 MIT 覆盖，可选 NVIDIA 运行库仍属专有软件，单独安装，不捆绑。

现有 0.4.5 安装包尚未包含本轮补齐的许可文本，不能认定已完成公开二进制分发审核。
发布安装包前仍需重建，并核实 Qt 的对应源码、库替换/重链接说明与许可通知，
FFmpeg 完整对应源码、外部/静态组件与构建配方，以及 MSVC runtime 的分发条件。
上游说明：[Qt LGPL 义务](https://www.qt.io/development/open-source-lgpl-obligations)、
[FFmpeg 分发说明](https://ffmpeg.org/legal.html)。详细来源见 [DEPENDENCIES.md](DEPENDENCIES.md) 和 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

## 验证限制

未重测真实摄像头、麦克风、物理快捷键、人工眼动精度、外部 AI 回答、Windows 10 或干净系统安装。
本轮没有重新生成或安装二进制；此前的安装验收记录不能替代本次新增许可资源的重建验证。
扫描结果针对本次候选文件，后续修改或新增文件需要重新检查。

```powershell
$env:LOOK_TO_ASK_TEST_CUDA = '1' # 仅已配置 GPU 的开发机
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/build_windows.py --source-only
```
