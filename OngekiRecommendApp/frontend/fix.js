
const fs = require('fs');
let content = fs.readFileSync('src/ExportControls.tsx', 'utf8');
content = content.replace(import html2canvas from 'html2canvas';, import domtoimage from 'dom-to-image-more';);
content = content.replace(
  /html2canvas\(tableElement\)\.then\(canvas => \{\s*const link = document\.createElement\('a'\);\s*link\.download = \ecommend_\$\{activeTab\}\.png\;\s*link\.href = canvas\.toDataURL\(\);\s*link\.click\(\);\s*\}\);/,
  domtoimage.toPng(tableElement, { bgcolor: '#ffffff', style: { margin: '0' } }).then(function (dataUrl) { const link = document.createElement('a'); link.download = \\\ecommend_\\\.png\\\; link.href = dataUrl; link.click(); }).catch(function (error) { console.error('Failed to export PNG', error); });
);
fs.writeFileSync('src/ExportControls.tsx', content);

