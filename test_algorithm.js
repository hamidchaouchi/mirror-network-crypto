const R_CLASSES = [1, 7, 11, 13, 17, 19, 23, 29];
const TAU = {1:-1.02359,7:-0.87441,11:-0.93203,13:-0.94951,17:-0.97712,19:-1.00318,23:-0.99274,29:-1.00836};

function isPrime(n) {
  if (n < 2) return false;
  if (n === 2) return true;
  if (n % 2 === 0) return false;
  for (let i = 3; i <= Math.sqrt(n); i += 2) if (n % i === 0) return false;
  return true;
}

function passesMod30(n) { return R_CLASSES.includes(n % 30); }

function passesResonance(n) {
  const r = n % 30;
  const tauR = TAU[r] !== undefined ? TAU[r] : 0;
  const ln_n = Math.log(n);
  const waves = R_CLASSES.map(rc => Math.cos((TAU[rc] + tauR) * ln_n));
  const re_fm = waves.reduce((a, b) => a + b, 0);
  const signal = re_fm / Math.sqrt(ln_n);
  const mean = re_fm / 8;
  const variance = waves.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / 8;
  const threshold = -0.55 / Math.log10(ln_n);
  return (signal < threshold) && (variance < 0.48);
}

let tp=0, tn=0, fp=0, fn=0;
for (let n = 7; n <= 10000; n++) {
  if (!passesMod30(n)) continue;
  const detected = passesResonance(n);
  const actual = isPrime(n);
  if (detected && actual)        tp++;
  else if (!detected && !actual) tn++;
  else if (detected && !actual)  fp++;
  else                           fn++;
}

console.log('=== نتائج اختبار الرنين الطيفي (7-10000) ===');
console.log(`TP (أولي كُشف):            ${tp}`);
console.log(`TN (مركب استُبعد):         ${tn}`);
console.log(`FP (مركب مرّ خطأً):        ${fp}`);
console.log(`FN (أولي استُبعد):         ${fn}`);
console.log(`دقة الرنين: ${((tp+tn)/(tp+tn+fp+fn)*100).toFixed(2)}%`);
console.log(`مركبة استُبعدت بنجاح:      ${tn}`);
console.log(`ضجيج باقٍ (تُوقفه MR):    ${fp}`);
