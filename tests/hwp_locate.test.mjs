// node tests/hwp_locate.test.mjs — XPath 해석·판정 규칙(원본 없이 실행).
import assert from 'assert';


import { parseXPath, pickMatch } from '../ui/conflict/hwp_locate.js';

assert.deepStrictEqual(parseXPath('/HwpDoc/BodyText/SectionDef[1]/ColumnSet/Paragraph[13]/LineSeg/TableControl/TableBody/TableRow[2]/TableCell[3]/Paragraph'), { sec: 0, para: 12, cellPara: 0 });
assert.deepStrictEqual(parseXPath('/HwpDoc/BodyText/SectionDef[2]/ColumnSet/Paragraph[4]'), { sec: 1, para: 3, cellPara: null });
assert.strictEqual(parseXPath('표 3행'), null);
assert.strictEqual(pickMatch([], '/HwpDoc/BodyText/SectionDef[1]/Paragraph[1]').status, 'not_found');
assert.strictEqual(pickMatch([{ sec: 0, para: 5 }], '/HwpDoc/BodyText/SectionDef[1]/Paragraph[1]').status, 'xpath_mismatch');
console.log('ok - XPath 해석·판정 규칙');
