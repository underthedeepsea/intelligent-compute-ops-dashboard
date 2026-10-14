const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {LocalCycle} = require('../refine-cycle.js');
const source = fs.readFileSync(path.join(__dirname, '../refine-app.js'), 'utf8');
const start = source.indexOf('function primeCycle()');
const end = source.indexOf('function updateCycleNote()', start);
assert.ok(start >= 0 && end > start, 'load the actual app refresh callback');

for (const refreshMs of [1000, 3000, 30000]) {
  test(`data repaint every ${refreshMs}ms preserves 30s wall-clock dwell`, () => {
    const rows = [{id:'a', status:'WARNING'}, {id:'b', status:'ERROR'}];
    let time = 0;
    const cycler = new LocalCycle();
    const context = vm.createContext({data:{}, screen:'02', cycler, endpointID:'a',
      selectedFault:'', allEndpoints:() => rows, epStatus:x => x.status,
      performance:{now:() => time}});
    vm.runInContext(source.slice(start, end), context);
    context.primeCycle();
    for (time = 1000; time <= 30000; time += 1000) {
      if (time % refreshMs === 0) context.primeCycle();
      const next = cycler.tick(time, rows, 'a', x => x.status, {scope:'02'});
      assert.equal(next, time === 30000 ? 'b' : null);
    }
  });
}
