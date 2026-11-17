import {samePaper} from '../evolve/paper-identity.js';
import {createLatestTask} from '../evolve/ui-task.js';
import {readableText,textHTML,paragraphsHTML} from '../evolve/text-format.js';
import {evolutionHash,parseRoute} from '../evolve/evolution-route.js';
import {repositoryInfo} from '../evolve/contribution-repository.js';
function equal(actual,expected){if(actual!==expected)throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`)}
function check(value,label){if(!value)throw new Error(label)}
equal(readableText('An \\textit{a priori} model with 10\\% gain and 4\\times speedup.'),'An a priori model with 10% gain and 4× speedup.');
equal(readableText('We use $\\textbf{x}_i \\times 2$.'),'We use $\\textbf{x}_i \\times 2$.');
equal(readableText('A \\textbf{nested \\textit{phrase}}.'),'A nested phrase.');
equal(readableText('See \\href{https://example.org/code}{the code}.'),'See the code (https://example.org/code).');
equal(paragraphsHTML('First paragraph.\n\nSecond paragraph.'),'<p>First paragraph.</p><p>Second paragraph.</p>');
const evil=textHTML('<img src=x onerror=alert(1)> \\href{javascript:alert(1)}{click}');
check(!evil.includes('<img'),'Raw source HTML must not become executable');
check(!evil.includes('href="javascript:'),'Source links must remain HTTP(S) only');
const linked=textHTML('Code: https://example.org/repo.');
check(linked.includes('href="https://example.org/repo"'),'Trailing punctuation is not part of a link');
check(linked.endsWith('</a>.'),'Keep punctuation visible');
const math=globalThis.katex.renderToString('x^2 + y^2', {throwOnError:false,trust:false});
check(math.includes('class="katex"'),'Bundled math renderer works');
const unsafe=globalThis.katex.renderToString('\\href{javascript:alert(1)}{click}',{throwOnError:false,trust:false});
check(!/<a\s/.test(unsafe),'Math must not create untrusted links');


const known={title:'CacheGen: KV Cache Compression',source_url:'https://arxiv.org/abs/2310.07240'};
check(samePaper({t:'Same paper, another version',u:'https://arxiv.org/pdf/2310.07240v2.pdf'},known),'ArXiv versions preserve paper identity');
check(!samePaper({t:'CacheGen: A different paper',u:'https://example.org/other'},known),'A title prefix must not select an unrelated example');
check(!samePaper({t:known.title,u:'https://example.org/different'},known),'Different explicit source URLs override coincidentally equal titles');
check(samePaper({t:'  CACHEGEN:  KV Cache Compression '},known),'A title-only record may match the complete normalized title');
check(!samePaper({u:'https://openreview.net/forum?id=one'},{source_url:'https://openreview.net/forum?id=two'}),'OpenReview paper IDs cannot be discarded');
const gate=createLatestTask(),painted=[];
function pending(){let resolve;const promise=new Promise(done=>{resolve=done});return {promise,resolve}}
function request(promise){const task=gate.begin();return promise.then(value=>{if(task.isCurrent())painted.push(value)})}
const first=pending(),second=pending(),firstWork=request(first.promise),secondWork=request(second.promise);
second.resolve('second paper');await secondWork;first.resolve('first paper');await firstWork;
equal(JSON.stringify(painted),JSON.stringify(['second paper']));
const leaving=pending(),leavingWork=request(leaving.promise);gate.cancel();leaving.resolve('paper after leaving the view');await leavingWork;
equal(JSON.stringify(painted),JSON.stringify(['second paper']));
print('Frontend text and math checks passed.');

const chosenPaper={u:'https://openreview.net/forum?id=paper&note=version'};
equal(parseRoute(evolutionHash(chosenPaper)).paper,chosenPaper.u);
equal(parseRoute(evolutionHash({source_url:chosenPaper.u})).paper,chosenPaper.u);
equal(parseRoute('#evolution').paper,null);
equal(parseRoute('').view,'evolution');
equal(parseRoute('#landscape').view,'map');
equal(parseRoute('#browse').view,'browse');
equal(parseRoute('#evolution?paper=javascript%3Aalert(1)').paper,null);
equal(parseRoute('#evolution?paper=%E0%A4%A').paper,null);
print('Evolution routes preserve paper identity across reload and history.');
equal(repositoryInfo({},'http://localhost:8765/contribute.html'),null);
equal(repositoryInfo({},'https://researcher.github.io/paper-evolve/contribute.html').url,'https://github.com/researcher/paper-evolve');
equal(repositoryInfo({},'https://researcher.github.io/contribute.html').repository,'researcher/researcher.github.io');
equal(repositoryInfo({repository:'team/research-graph'},'https://example.org/contribute.html').forkURL,'https://github.com/team/research-graph/fork');
equal(repositoryInfo({repository:'https://untrusted.example/key'},'http://localhost/'),null);
equal(repositoryInfo({},'https://researcher.github.io/%2e%2e/contribute.html'),null);
equal(repositoryInfo(null,'http://localhost/'),null);
print('Contribution repository links respect explicit identity and Pages project paths.');
