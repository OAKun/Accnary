# Accnary Phase 1 实现与测试报告

日期：2026-10-24
状态：**完成**。全量回归 79/79 通过（Phase 0：16，Phase 1：63）。

## 1. 交付内容

按既定优先级完成三块核心能力，全部在 `frame/` 开发根内：

### 1.1 安全存储层（app/storage/）

- `KdbxVault`：创建 / 解锁 / 锁定 / 主密码修改；**安全保存六步流程**
  （冲突检测 → 加密临时文件 → 重开验证结构 → 旧版加密快照 .bak →
  原子替换 → 失败即回滚清理）。中途断电/杀进程最多遗留一个临时文件，
  会在下次打开时清理，正式文件永远完整。
- **并发修改检测**：打开时记录文件 SHA-256，保存时比对；被 KeePassXC
  或另一实例抢先修改过则拒绝覆盖（`ConflictError`），必须 `reopen()`
  重读后再改——已实测覆盖。
- **加密备份/恢复**：备份即加密文件校验副本（无明文中间态）；恢复必须
  `confirmed=True` 显式确认，恢复前自动保留 pre-restore 快照。
- **故障注入测试**：模拟 `os.replace` 失败、磁盘满（ENOSPC）——两种
  场景下原文件字节级完好、临时文件被清理。

### 1.2 完整账户模型（app/models/ + app/services/）

四层结构 Service → Account → LoginMethod / Identity / License：

- 平台（别名/类型/多网址/分类/标签）映射为 KDBX 组；账户映射为条目；
  标准字段承载用户名/密码/网址/备注。
- 每账户多种登录方式并存（密码 / 邮箱 / 手机验证码 / 微信 / QQ /
  Google / Apple / SSO / Passkey / 自定义），互不推断。
- **身份注册表**：微信/QQ/手机号/邮箱等身份全局登记一次（根组系统条目），
  账户以稳定 UUID 引用；邮箱绑定按 注册/登录/当前/找回 四种角色分开；
  反向查询"哪些账户绑定了这个微信号"为原生能力；身份永不自动合并。
- 付费授权：购买类型/渠道/订单号/激活码/有效期/设备数，全部位于加密
  Meta 内。已验证密钥等敏感值不出现在文件明文中（字节级泄露扫描测试）。
- 无密码账户是一等公民；同平台多账户、多登录方式、自定义字段全部
  往返无损。
- `CatalogService` 是唯一门面：未来 UI 只通过它操作密码库，不触碰
  KDBX 细节。

### 1.3 数据兼容性

- `Accnary.SchemaVersion` 标记 + 迁移注册表：低版本可迁移读取（机制
  已测）；**高版本拒绝写回**（read-only 化，防止新字段被旧程序抹掉）。
- **KDBX 4.1 写入保护**：合成 4.1 头部文件实测——可读、所有写入被拒、
  文件字节不变。
- **KDBX 3.x 只读**：实测 KeePassXC 2.8.0 CLI `db-create` 默认产出
  3.1 + AES-KDF 库——Accnary 能打开，但拒绝写入。
- **未知字段保留**：外部工具写入的自定义属性（含中文键）在 Accnary
  多次保存后逐字节保留；非托管条目只计数、不动内容。
- **KeePassXC 回归**（真实存储层重建）：Accnary 建库（含注册表+完整
  账户）→ KeePassXC 读取 → KeePassXC 修改保存 → Accnary 重开校验
  （UUID/许可证/登录方式/身份标签/注册表全部完好，格式仍 4.0）→
  Accnary 再写 → KeePassXC 再读。双向全通。

### 1.4 密码生成器（app/security/）

基于 `secrets`（OS CSPRNG）：长度/字符类/排除相似字符/自定义字符集/
必含每类策略，边界与统计测试通过。

## 2. 实现期发现（已消化进实现）

1. **pykeepass 的 `delete_entry` 是永久删除**——已改用 `trash_entry`
   （KDBX 标准回收站）+ `move_entry` 恢复，UUID 跨回收站稳定。
2. pykeepass `find_entries/find_groups` 的 `uuid` 参数需要 `UUID`
   对象；保护标志查询 API 名为 `is_custom_property_protected`。
3. **KeePassXC 2.8.0 CLI 建库默认 KDBX 3.1 + AES-KDF**（非 Argon2）；
   顺手成为 3.x 只读守卫的真实测试样本。
4. KDBX 4 头部含 SHA-256 + HMAC 双校验：篡改即 `HeaderChecksumError`
   干净拒识（损坏文件测试依据）；合成 4.1 样本需同步重算两者。
5. pykeepass 生成的条目 UUID 是 uuid1 风格（含 MAC 信息）；Accnary
   自身生成的身份/登录方式 UUID 均为 uuid4。

## 3. 已知限制与风险（进入 Phase 2 前知情）

| # | 限制 | 处置 |
|---|---|---|
| L1 | Python 内存无法保证彻底擦除凭据字符串 | 减少副本/短生命周期/不落盘；文档明示不承诺内存擦除 |
| L2 | 服务属性以"组内首个带 Meta 的条目"为准合并；条目间服务块不一致时不仲裁 | Phase 3 搜索/详情层统一展示口径 |
| L3 | 注册表条目被外部删除后身份清单丢失（悬空引用会报告，账户数据无损） | Phase 2 提供注册表健康提示；不考虑自动重建身份 |
| L4 | 保存存在 TOCTOU 窗口（哈希检查与原子替换之间） | 单用户桌面场景风险极低；替换是原子的，最坏情形走 ConflictError 路径 |
| L5 | GUI 层 KeePassXC 属性编辑核对未做（CLI 无法覆盖） | 列入 Phase 2 手动验收 |
| L6 | 冲突解决只有"整体 reload"策略，无条目级合并 | v0.1 定位为个人单机工具，够用；多实例合并列入远期 |

## 4. 测试结果

```
frame $ .venv/Scripts/python -m pytest tests/
79 passed (Phase 0: 16 + Phase 1: 63)   约 2 分 44 秒
```

Phase 1 覆盖：模型序列化与迁移（10）、密码库生命周期（7）、安全保存
与故障注入（8）、加密备份恢复（6）、兼容守卫（5）、CatalogService
功能（17）、密码生成器（9）、KeePassXC 回归（1）。

## 5. 下一步：Phase 2（Qt 桌面界面）

- 主窗口三栏布局（导航 / 账户列表 / 详情）、新建/编辑账户（渐进式表单）
- 应用图标已就位：`frame/assets/app-icon.png`（蓝色钥匙孔字母 A）
- 主密码解锁窗、锁定态、托盘雏形
- 界面全部通过 CatalogService 门面操作，Phase 1 测试继续作为回归底线
