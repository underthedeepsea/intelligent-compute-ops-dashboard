> 当前访问合同以 [v0.4.0直接访问设计](direct-access-design.md) 为准，无账号初始化，HTTP Pod IP:8080直接使用。

# HTTP Pod 直连部署实施计划

1. 记录用户新的HTTP合同，冻结历史账本与两个受保护数据库，保留原部署预算；本次限定2候选/2审查。
2. Sol61 medium实现独立传输选择、HTTP overlay/迁移profile及定点测试，根协调者更新README与现场准备清单；文件所有权分离。
3. 验证普通HTTP匿名直接访问、CSRF Cookie、CSRF/跨源、完整性边界、伪造协议头、无效配置、原HTTPS默认；只使用临时SQLite。
4. 离线渲染HTTP应用/迁移清单，核对Nginx挂载、0.4.0镜像一致、无Ingress/证书资源、单写者、存储/权限与可写tmp，沿用官方本地schema进行严格验证。
5. 一次Sol61 medium独立集中Review；有阻塞finding时记录并限定剩余批次，不自动扩大预算或提高档位。
6. 一次Final Audit和历史/数据库哈希核对，记录实际验证及AMD64/真实NAS限制。用户已取消镜像上传，不自动恢复上传流程；发布v0.2.0标签不改。
