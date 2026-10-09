> 当前访问合同以 [v0.4.0直接访问设计](direct-access-design.md) 为准，无账号初始化，HTTP Pod IP:8080直接使用。

# HTTP Pod 直连部署设计

日期：2026-10-09。用户明确选择纯 HTTP；Pod IP 在其环境中外部可达，不要求 Ingress、TLS、证书或 HTTPS 跳转。

这是已交付 v0.2.0 之后的传输合同变更。历史 docker-nas-deployment-v1 的失败、冻结、候选2/2和审查2/2不修改，不把其已知问题重开为新任务。

## 合同

- `CONTROL_TRANSPORT` 仅允许 `http`/`https`，非本地默认仍为 `https`，本地行为保持兼容。
- HTTP 明确关闭 CSRF Cookie 的 Secure 属性，使普通浏览器能携带CSRF token；不启用 DEBUG、LOCAL 或演示导入，采用匿名直接访问全部环境并保留 CSRF 校验。
- HTTP Django 不信任 `X-Forwarded-Proto`；直连 Web 的 Nginx 按自身 `$scheme` 覆盖外部转发协议头。原 HTTPS 配置保留在原 base/nginx.conf。
- `deploy/k8s/http` 引用原 base，应用配置选择 HTTP，挂载独立 Nginx ConfigMap；8080 Web、8000 API。API Service 和集群 DNS保留，不创建 Ingress/TLS Secret。
- HTTP迁移清单复用原维护Job，镜像与HTTP应用同版本；HTTP路线使用待构建版本0.4.0，不能配旧0.2.0镜像宣称支持新增配置。
- NAS PV/PVC、DELETE/FULL、单副本单worker、Recreate及唯一维护写者合同不变。全部测试使用临时库，不修改原库/8767库。
- 本次不上传镜像、不部署真实集群；AMD64成品和现场NAS验证仍待部署者完成。HTTP访问地址重建更新和网络可达性由现场提供。

参考：[Django Cookie配置](https://docs.djangoproject.com/en/5.2/ref/settings/#session-cookie-secure)、[代理协议头](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header)、[CSRF](https://docs.djangoproject.com/en/5.2/ref/csrf/)。
