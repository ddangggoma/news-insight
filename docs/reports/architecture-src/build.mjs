import {build} from 'esbuild';import fs from 'node:fs';
import path from 'node:path';import {fileURLToPath} from 'node:url';
process.chdir(path.dirname(fileURLToPath(import.meta.url)));fs.mkdirSync('.build',{recursive:true});
await build({entryPoints:['app.jsx'],bundle:true,minify:true,outfile:'.build/bundle.js',define:{'process.env.NODE_ENV':'"production"'},legalComments:'eof',loader:{'.css':'css'},jsx:'automatic'});
const data=fs.readFileSync('.build/data.json','utf8').replace(/</g,'\\u003c');
const html=`<!doctype html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta name="color-scheme" content="light dark"><title>NEWS INSIGHT — 인터랙티브 시스템 아키텍처</title><style>${fs.readFileSync('.build/bundle.css','utf8')}</style></head><body><div id="root"></div><noscript>그래프 탐색에는 JavaScript가 필요합니다. 기존 상세 보고서 HTML을 열어 설명을 확인하세요.</noscript><script id="atlas-data" type="application/json">${data}</script><script>${fs.readFileSync('.build/bundle.js','utf8').replace(/<\/script/gi,'<\\/script')}</script></body></html>`;
fs.writeFileSync('../news-insight-architecture.html',html);console.log('HTML bytes:',Buffer.byteLength(html));
