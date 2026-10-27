# Accnary Phase 0 技术与安全验证报告

日期：2026-10-24
状态：**通过**（含 KeePassXC 双向互操作验证，无遗留阻塞项）

## 1. 结论

PySide6 + PyKeePass 技术栈在本机验证可行。KDBX 4.0 的创建、读写、主密码修改、
自定义字段（含中文 JSON）、条目历史、附件、UUID 稳定引用全部通过自动化往返测试；
Accnary（pykeepass）与 KeePassXC 2.8.0 的**双向读写互操作**也已用官方便携版实测
通过。可以进入 Phase 1（正式工程与核心功能）。

**尚未解锁**：真实密码迁入。需先完成 Phase 1 工程化封装和 Phase 4 安全复核
（本次验证全部使用虚构数据）。

## 2. 已锁定技术栈

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.14.9 | 本机 `D:\Programs\Python\python.exe`，项目独立 venv |
| PySide6-Essentials | 6.12.0 / Qt 6.12.0 | 仅装 Essentials，不含 WebEngine/Addons，符合轻量打包约束 |
| pykeepass | 4.2.0 | KDBX 引擎，纯 Python（GPL-3.0，见第 5 节） |
| pytest | 9.1.1 | 测试框架（dev 依赖） |
| KeePassXC | 2.8.0（官方便携版） | 仅作互操作验证工具，非运行依赖；解压于 `tools/keepassxc-portable/`（gitignore） |

- 传递依赖（construct、lxml、pycryptodomex、argon2-cffi、pyotp 等）一并锁定。
- 锁定文件：[requirements-lock.txt](../requirements-lock.txt)，19 个包全部带
  sha256 哈希，可用 `pip install --require-hashes -r requirements-lock.txt` 复现。
- pykeepass 未发现公开 CVE；生态内主要风险来自恶意构造的 .kdbx 导致解析器崩溃
  （KeePass 系 CVE-2026-86776 一类），需在 Phase 1 增加"非法文件拒绝打开"测试并
  持续跟踪 GitHub advisories / OSV。
- KeePassXC 便携版 ZIP 下载自官方 GitHub release
  （keepassxreboot/keepassxc，tag 2.8.0），SHA-256
  `48ff4f088e9ce70e241da1270e5081528dba77c38b17dae4aa6690ffc50fc828`
  与官方 `.DIGEST` 校验文件一致；解压后仅保留便携目录，ZIP 已删除。

## 3. 自动化验证结果（16 项全部通过）

运行方式：`.venv/Scripts/python -m pytest tests/phase0 -v`

### 3.1 KDBX 创建与读取（test_kdbx_create_read.py）

| 用例 | 结果 |
|---|---|
| 创建库 → 重新打开 → 标准字段 + `Accnary.*` 自定义字段（中文 JSON）完整 | ✅ |
| 加密配置：KDBX **4.0** + **AES-256** + **Argon2d**（V=19, M=64MiB, P=2, I=14） | ✅ |
| 错误主密码 → `CredentialsError` 拒绝 | ✅ |
| 主密码修改 → 新密码可开、旧密码被拒 | ✅ |
| 同平台多账户（同 Title 不同 username，UUID 不同） | ✅ |

### 3.2 特性保留（test_kdbx_features.py）

| 用例 | 结果 |
|---|---|
| `Accnary.*` 命名空间自定义字段经多次保存往返后逐字节保留（含中文、嵌套 JSON） | ✅ |
| 条目历史（`save_history`）：历史密码、历史自定义字段保留 | ✅ |
| 附件（含 `\x00`/`\xff` 的二进制）保存重开完整 | ✅ |
| UUID 稳定 + `find_entries(uuid=...)` 可用 | ✅ |
| 身份反向查询：两个条目引用同一微信身份 UUID，全库扫描可反查 | ✅ |

### 3.3 PySide6 冒烟（test_pyside6_smoke.py）

QApplication 启动、控件文本往返、offscreen 渲染出非空 pixmap、QMainWindow、
高 DPI 属性查询全部通过。仅证明技术栈可用，**不含任何界面设计**。

### 3.4 KeePassXC 双向互操作（test_keepassxc_interop.py，2.8.0 便携版 CLI）

完整验收场景一次通过：

1. Accnary 写入库：软件密码 + 微信登录 + 绑定手机号 + 找回邮箱 + 付费许可证（全虚构）；✅
2. KeePassXC `ls` 看到条目、`show -a Accnary.Meta` 读出完整 JSON；✅
3. KeePassXC `edit --notes` 修改并保存 —— **整库由 KeePassXC 写出**；✅
4. Accnary 重开：UUID 不变、KeePassXC 的修改可见、`Accnary.Meta` 逐字节保留；✅
5. Accnary 修改自定义字段保存，KeePassXC 再读回成功。✅

**格式稳定性**：KeePassXC 2.8.0 保存后文件仍为 KDBX 4.0 / AES-256 / Argon2d，
未发生版本升级，pykeepass 无障碍重开。

## 4. 关键发现

1. **KDF 默认为 Argon2d，非 Argon2id。** pykeepass 4.2.0 能*读取* Argon2id，
   但 `create_database` 无参数选择 KDF。Argon2d 是 KeePassXC 2.7 的默认值，
   对本地单机场景差异极小；KeePassXC 官方也承认 Argon2d 的兼容性与安全性。
   处置：v0.1 接受 Argon2d；Phase 1 研究"保存前安全改写 KDF 参数"的可行性并
   单独测试，不作为阻塞项（保留调整空间）。
2. **KDBX 4.1 仅部分支持。** pykeepass 4.x 宣布部分支持 4.1 特性。Accnary
   v0.1 策略：**只创建 KDBX 4.0 库**；遇到更高版本/未知字段时只读或拒绝写回，
   该守卫逻辑在 Phase 1 用构造样本测试。本次实测 KeePassXC 2.8.0 保存后
   仍是 4.0，暂未触发此边界。
3. **`create_database` 复用打包的 blank_database.kdbx**，KDF 参数即其默认值
   （M=64MiB、P=2、I=14）。正式发布前按安全审查结论调参（属 Phase 1）。
4. **KeePassXC 2.8.0 CLI 移除了 `--pw-stdin`**：非 TTY 运行时自动从 stdin 读
   数据库密码。互操作测试已按 2.8.0 适配；若换回 2.7.x 需恢复该标志。
5. **KeePassXC CLI 不支持写自定义属性**（`edit` 仅支持 title/username/url/notes/
   password）。GUI 才能编辑 custom attributes。因此自动化互操作用"改备注触发
   整库保存"验证写入路径；GUI 层面的属性编辑核对列入 Phase 2 手动验收。

## 5. GPL-3.0 许可证评估（pykeepass）

- **个人本地使用、不分发**：无任何义务，v0.1 现状即如此。
- **将来分发 EXE**（打包 pykeepass 字节码）：组合作品须遵守 GPL-3.0 ——
  提供对应源码、以 GPL 兼容方式许可、保留版权声明。届时 Accnary 自身许可
  需要用户决策（GPL-3.0 / 仅私有使用声明 / 其他）。
- 进程外调用 KeePassXC CLI 的替代方案可规避链接争议，但功能受限、体验差，
  仅作备选记录。
- **决策点保留给用户**，在准备分发前回到此项。
- KeePassXC 本身是 GPL-3.0，但仅作为独立验证工具使用、不分发、不链接，
  不对 Accnary 产生许可义务。

## 6. 风险清单（进入 Phase 1 前必须知情）

| # | 风险 | 等级 | 处置 |
|---|---|---|---|
| R1 | Python 无法保证彻底擦除内存中的明文凭据（字符串不可变、解释器存在副本） | 已知共性 | 减少副本、缩短生命周期、不写日志/不落盘；文档明确"不宣称内存彻底清除" |
| R2 | Windows 剪贴板历史（Win+V）可能留存复制的密码 | 中 | Phase 3 实现定时清除（不覆盖用户新复制内容）+ 界面提示 |
| R3 | ~~KeePassXC 互操作未实测~~ | ~~高~~ | **已消除**：2.8.0 双向互操作实测通过（第 3.4 节） |
| R4 | 恶意 .kdbx 触发解析器崩溃/异常 | 中 | Phase 1 增加"损坏/非法文件拒绝打开且不写回"测试 |
| R5 | pykeepass 对 KDBX 4.1 特性支持不完整 | 中 | 只写 4.0；高版本文件只读/拒绝写回（Phase 1 守卫测试） |
| R6 | GPL-3.0 分发义务 | 低（当前不分发） | 分发前由用户决策许可方案 |
| R7 | pykeepass 依赖链安全更新 | 低 | 锁定文件 + 定期审计（pip-audit 纳入 Phase 4） |
| R8 | GUI 层 KeePassXC 自定义属性编辑核对未做（CLI 无法覆盖） | 低 | Phase 2 手动验收清单加入：GUI 打开 Accnary 库核对 Attributes |

## 7. 下一步：Phase 1 计划

1. `app/storage/`：KdbxVault 封装 —— 创建/解锁/保存/锁定/冲突检测/安全保存六步流程；
2. `app/models/`：Service → Account → LoginMethod/Identity/License 四层数据模型，
   含 `Accnary.SchemaVersion` 迁移钩子；
3. `app/services/`：账户操作与内存搜索索引（解锁后构建、锁定即清除）；
4. Phase 0 测试改造为 storage 层的回归测试；新增冲突恢复、损坏文件、
   KDBX 4.1 守卫用例；
5. 完成后进入 Phase 2（Qt 主窗口）。
