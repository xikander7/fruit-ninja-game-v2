// The Ki meter (ninja/powers.py): filled by cuts, spent on a superpower.
export const KI_MAX = 100;
export const KI_PER_CUT = 4;
export const KI_PER_COMBO = 3; // x combo size, for combos of 3 or more

export class KiMeter {
  constructor(value = 0) {
    this.value = value;
    this.locked = false; // set while a power runs: powers never feed the meter
  }
  get full() {
    return this.value >= KI_MAX;
  }
  add(n) {
    if (!this.locked) this.value = Math.min(KI_MAX, this.value + n);
  }
  spend() {
    this.value = 0;
  }
}
