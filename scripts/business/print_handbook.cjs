const { mkdirSync } = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const docs = path.resolve(__dirname, '../../docs/06_Pilot');
const output = path.join(docs, 'pdf');
const html = pathToFileURL(path.join(docs, 'SO_TAY_AGENT1.html')).href;

async function printHandbook() {
    const browser = await chromium.launch({ headless: true, channel: 'msedge' });
    try {
        const page = await browser.newPage();
        await page.goto(html);
        await page.addStyleTag({ content: `
            @page{size:A4;margin:14mm 14mm 17mm}
            @media print{
                body,main{font:10.8pt/1.5 'Segoe UI',Arial,sans-serif}
                h1{font:650 34pt/1.2 'Segoe UI',Arial,sans-serif;margin:26mm 0 8mm}
                h2{font-size:20pt;break-before:page;margin:0 0 8mm;padding-top:4mm}
                h3{font-size:18pt;break-before:page;margin:0 0 5mm}
                h2+h3{break-before:auto}
                p,ul,ol{margin-top:3mm;margin-bottom:3mm}li+li{margin-top:1.3mm}
                table{font-size:9.6pt;line-height:1.38}th,td{padding:6px 8px}td:first-child{width:24%}
                .table-frame{overflow:visible}figure{padding:2.5mm;margin:4mm 0;border-radius:2mm}
                figure svg{max-height:115mm;overflow:hidden}figcaption{font-size:9.3pt;line-height:1.38}
                figure[data-shot='11-import.png'] svg{max-height:86mm}
                figure[data-shot='17-forecast-form.png'] svg{max-height:103mm}
                figure[data-shot='18-base-result.png'] svg{max-height:78mm}
                figure[data-shot='19-weekly.png'] svg{max-height:70mm}
                figure[data-shot='23-export.png'] svg{max-height:19mm}
                a{overflow-wrap:anywhere}p{orphans:3;widows:3}footer{margin-top:6mm;font-size:8.5pt}
            }
        ` });
        mkdirSync(output, { recursive: true });
        await page.pdf({
            path: path.join(output, 'So-tay-Agent1.pdf'),
            format: 'A4',
            printBackground: true,
            displayHeaderFooter: true,
            headerTemplate: '<span></span>',
            footerTemplate: `<div style="width:100%;padding:0 14mm;font:9px Segoe UI;color:#53645d;display:flex;justify-content:space-between"><span>AGENT1 · THỰC HÀNH ĐẠI PHÁT</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
        });
    } finally {
        await browser.close();
    }
}

printHandbook().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
