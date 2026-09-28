import assert from 'node:assert/strict';
import {nextLaunchDelay,launchFrame,LAUNCH_DURATION} from '../bot/static/dashboard/sovereign-launch.js';
assert.equal(nextLaunchDelay(()=>0),600000);assert.equal(nextLaunchDelay(()=>1),900000);
for(let i=0;i<1000;i++){const delay=nextLaunchDelay();assert(delay>=600000&&delay<=900000);}
assert.equal(launchFrame(0).rise,0);assert.equal(launchFrame(2.9).rise,0);assert(launchFrame(2).flame>launchFrame(1).flame);
const p=[4,5,6,7].map(t=>launchFrame(t).rise);assert(p[3]-p[2]>p[2]-p[1]);
assert.equal(launchFrame(20).phase,'ascent');assert.equal(launchFrame(24).phase,'clearing');assert.equal(launchFrame(24).rocket,false);
assert(launchFrame(40).smoke>launchFrame(55).smoke);assert.equal(launchFrame(LAUNCH_DURATION).smoke,0);
console.log('Launch ignition, acceleration, smoke decay and 10–15 minute timing passed');
