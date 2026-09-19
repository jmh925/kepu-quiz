const fs = require('fs');
const html = fs.readFileSync('demo/index.html', 'utf8');
const re = /<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g;
const code = re.exec(html)[1];
const lines = code.split('\n');
console.log('生成产物中相关行：');
lines.forEach((l, i) => {
  if (/search\(|replace\(\/\/|test\(inner\.trim/.test(l)) {
    console.log('  ' + (i + 1) + ': ' + JSON.stringify(l.trim()));
  }
});
const src = fs.readFileSync('tools/make_demo.js', 'utf8').split('\n');
console.log('\n生成器源文件中相关行：');
src.forEach((l, i) => {
  if (/search\(|replace\(\/\\\/\$\/|test\(inner\.trim/.test(l)) {
    console.log('  ' + (i + 1) + ': ' + JSON.stringify(l.trim()));
  }
});
