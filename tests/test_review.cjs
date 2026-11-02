const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map();
function node(selector) {
  if (!nodes.has(selector)) nodes.set(selector, {
    checked: false, value: '', textContent: '', innerHTML: '', hidden: false,
    style: {}, classList: {add(){}, remove(){}, toggle(){}},
  });
  return nodes.get(selector);
}
const context = vm.createContext({
  window: {}, document: {querySelector: node, querySelectorAll: () => []},
  localStorage: {getItem: () => '[]'}, setTimeout, clearTimeout,
});
vm.runInContext(fs.readFileSync('review.js', 'utf8'), context);
vm.runInContext("result={noteCount:100, recognitionMode:'pdf-optimized-350+crosscheck', validation:{crossCheck:{differingMeasureCount:2,measuresCompared:10}}}; file={name:'score.pdf'};", context);
assert.equal(vm.runInContext('accuracy()', context), null, 'No accuracy claim before review');
node('#reviewComplete').checked = true;
assert.equal(vm.runInContext('accuracy()', context), 100);
vm.runInContext("marks=[{category:'wrongPitch'}]", context);
assert.equal(vm.runInContext('accuracy()', context), 99);
assert.equal(vm.runInContext('report().reviewComplete', context), true);
vm.runInContext('showResult()', context);
assert.equal(node('#reviewComplete').checked, false, 'New result requires a new review');
assert.equal(node('#statMode').textContent, 'Optimized PDF');
assert.match(node('#crossCheckBox').textContent, /2 of 10/);
assert.equal(vm.runInContext('report().estimatedNoteAccuracy', context), null);
console.log('Test Lab review state, cross-check summary, and PDF mode checks passed');
