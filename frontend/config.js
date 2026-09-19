/**
 * 后端接口地址配置
 *
 * 本地联调：保持 127.0.0.1，并在「微信开发者工具 → 详情 → 本地设置」中
 *           勾选「不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书」。
 * 上线部署：改成已备案的 https 域名，并在小程序后台配置 request 合法域名。
 */
const IS_DEV = true;

module.exports = {
  IS_DEV: IS_DEV,
  BASE_URL: IS_DEV
    ? 'http://127.0.0.1:8000/api/v1'
    : 'https://your-domain.com/api/v1'
};
