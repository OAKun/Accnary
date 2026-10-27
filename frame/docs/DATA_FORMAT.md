# Accnary 数据格式说明（Accnary Meta Schema v1）

Accnary 的唯一权威数据源是一个标准 **KDBX 4.0** 密码库文件
（AES-256 加密 + Argon2d 密钥派生）。Accnary 不创建任何明文数据库、
索引或配置副本；所有结构化信息都存在 KDBX 条目的加密自定义字段里。

## 1. KDBX 结构映射

```
Root (KDBX 根组)
├── Accnary Identity Registry        ← 系统条目：身份注册表（见 §4）
├── <平台/服务 A> (KDBX Group)       == 一个 Service（平台）
│   ├── <Entry 1>                    == 该平台的一个 Account
│   └── <Entry 2>                    == 同平台的另一个 Account
├── <平台/服务 B> (KDBX Group)
│   └── ...
└── Recycle Bin                      ← KDBX 标准回收站（删除的条目可恢复）
```

- **Group = Service**：组名即平台名，也是条目标题（Entry.Title）。
  组名在加载时具有最高优先级（用户在 KeePassXC 里重命名分组仍然有效）。
- **Entry = Account**：一个登录身份对应一个条目；同平台多账户 =
  同组内多个条目（KeePassXC 里以用户名区分）。
- 标准字段复用：`UserName`=用户名，`Password`=密码（可为空），
  `URL`=主登录网址，`Notes`=备注，`Title`=平台名。
- **Recycle Bin** 中的条目不是账户；未带 Accnary 标记的条目/组是
  "非托管内容"——Accnary 永远原样保留它们，不索引、不删除、不重写。

## 2. 条目自定义字段

每个 Accnary 托管的条目带两个受 `Accnary.` 命名空间保护的自定义属性：

| 属性 | 内容 |
|---|---|
| `Accnary.SchemaVersion` | schema 版本号（十进制字符串），兼容性守卫的依据 |
| `Accnary.Meta` | JSON 载荷（schema v1，见 §3） |

用户自定义字段直接存为普通 KDBX 自定义属性（KeePassXC 可见可编辑，
可加 `Protected` 标志）。以 `Accnary.` 开头的键被 Accnary 保留，
用户字段禁止使用。

## 3. Accnary.Meta JSON（schema v1）

```jsonc
{
  "schema_version": 1,
  "service": {                       // 平台信息（组名的镜像 + 扩展属性）
    "name": "DemoCloud",             // 冗余存储；加载时以组名为准
    "aliases": ["DC"],
    "type": "cloud_service",         // website|desktop_app|mobile_app|
                                     // research_platform|journal_system|
                                     // dev_platform|cloud_service|server|other
    "urls": ["https://cloud.example.com"],
    "login_urls": ["https://cloud.example.com/login"],
    "category": "云服务",
    "tags": ["网盘"],
    "notes": ""
  },
  "account": {
    "uuid": "…",                     // 与 Entry UUID 一致（Entry 为准）
    "user_id": "", "alias": "",
    "email": "",                     // 注册邮箱快捷字段（可检索）
    "phone": "",                     // 注册手机号快捷字段（可检索）
    "favorite": false,
    "last_used_at": null,            // ISO-8601，复制凭据时刷新
    "login_methods": [               // 多种登录方式并存
      {"uuid": "…", "type": "password", "note": "",
       "identity_ref": null, "extra": ""},
      {"uuid": "…", "type": "wechat_oauth", "identity_ref": "<身份UUID>",
       "note": "扫码登录", "extra": ""}
    ],
    "identity_bindings": [           // 与身份的绑定关系（角色区分）
      {"identity_ref": "<身份UUID>", "role": "login_phone"},
      {"identity_ref": "<身份UUID>", "role": "recovery_email"}
    ],
    "license": {                     // 付费授权（全部在加密区内）
      "mode": "subscription",        // none|perpetual|subscription|trial|license_key
      "purchase_date": "2026-01-01", "channel": "官网", "order_no": "",
      "license_key": "", "expires": "2027-01-01",
      "device_limit": null, "evidence": "", "notes": ""
    }
  }
}
```

### 约定

- **登录方式类型** `type`：password / email_password / phone_password /
  phone_sms / wechat_oauth / qq_oauth / google_oauth / apple_oauth / sso /
  passkey / custom。未知值读取时回落为 custom（服务类回落 other），
  不报错、不丢数据。
- **绑定角色** `role`：邮箱四分（registration_email / login_email /
  current_email / recovery_email）+ login_phone / recovery_phone /
  linked_identity。
- **身份引用**：`identity_ref` 一律是身份注册表中的稳定 UUID 字符串。
  登录方式与绑定关系分开存储；绝不用"某平台支持微信登录"来推断两个
  账户属于同一身份。
- **未知键保留**：读取时未知字段进入 `_extra`，写回时原样输出。
  v1 内部子结构视为封闭；结构变更必须升版本。
- 用户名/密码/网址/备注**只存标准字段**，不在 Meta 中重复，避免双源漂移。

## 4. 身份注册表条目

根组下标题为 `Accnary Identity Registry` 的条目，带
`Accnary.System = "identity-registry"` 标记，其 Meta：

```jsonc
{
  "schema_version": 1,
  "identities": [
    {"uuid": "…", "kind": "wechat",      // email|phone|wechat|qq|other
     "label": "微信主号", "value": "", "notes": ""}
  ]
}
```

- 身份全局唯一、只登记一次；账户通过 UUID 引用。
- 引用是显式的：删除仍被引用的身份会被拒绝（force 删除后引用悬空并在
  加载时报告 `dangling_identity_refs`，账户数据不受影响）。
- 身份之间不自动合并。

## 5. 版本管理与兼容性契约

1. **向后读**：`schema_version` 低于当前版 → 逐版本执行注册的迁移函数
   （`serialization.register_migration`）后再解析。
2. **向前拒写**：`schema_version` 高于当前版 → 目录标记 read-only，
   所有修改与保存被拒绝（`SchemaTooNewError`），新版本字段不会被旧
   程序抹掉。
3. **格式守卫**：Accnary 只写 KDBX 4.0。打开 3.x（含 KeePassXC CLI
   `db-create` 的默认产物）或 4.1+ 文件时可读，但所有写操作被
   `UnsupportedFormatError` 拒绝，文件字节保持不变。
4. **未知字段**：非 Accnary 的自定义属性（含 KeePassXC 添加的）在
   Accnary 的任何保存后原样保留。
5. **损坏防护**：文件被篡改/截断时 KDBX 校验失败 →
   `VaultFormatError` 干净拒绝，文件不做任何"修复"。

## 6. 安全保存流程（写入路径）

1. 校验磁盘文件自打开以来未被外部修改（SHA-256 比对），否则
   `ConflictError`，需 `reopen()` 后重做；
2. 完整加密写入同目录临时文件 `*.accnary-tmp-<pid>`；
3. 重新打开临时文件，比对条目/组结构，验证失败即放弃；
4. 把旧文件复制为 `<name>.kdbx.bak`（始终是加密快照）；
5. `os.replace` 原子替换；
6. 任一步失败：删除临时文件并报 `SafeSaveError`，上一版本完好。

打开时自动清理遗留的临时文件。备份 = 加密文件的校验副本
（`export_backup`），恢复需 `confirmed=True` 显式确认，且恢复前自动
保留 `<name>.kdbx.pre-restore.bak`。
