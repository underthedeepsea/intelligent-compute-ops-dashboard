# v0.4.0 直接访问实施

实施以 [直接访问设计](direct-access-design.md) 为准。API将请求操作来源固定为anonymous，scoped返回完整集合，环境从全部实体汇总；移除账号授权判断并保持数据完整性校验。前端统一ensureAccess与can_write，独立资源录入同步更新，去除admin链接和账号提示，HTML资源版本为direct-access-v1。

数据库不需要清理身份或新数据迁移；原admin迁移图通过LegacyAdminConfig兼容保留。CLI导入来源字符串独立于User；两种bootstrap命令退休。部署模板统一0.4.0，迁移只migrate，Nginx撤login和admin代理。默认HTTP升级遵守原NAS停写、备份、唯一迁移、全部进程退出后恢复的顺序；备份Python片段逐字保留。

验证使用临时SQLite及非LOCAL生产HTTP进程，不接生产系统；当前后端全套、JS及真实浏览器结果记录在新episode evidence。历史证据不改。实际AMD64成品、现场K8s/NAS和生产来源验收不在本地验证结论内。
