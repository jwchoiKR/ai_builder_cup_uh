// AudioWorklet: microphone float samples -> 16 kHz mono 16-bit PCM, 100 ms frames (DEV_SPEC §10.1).
// Downsampling averages the input samples of each output sample (a box filter against aliasing).
class PcmWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.frame = new Int16Array(1600);
    this.n = 0;
    this.pos = 0;
    this.acc = 0;
    this.count = 0;
    this.energy = 0;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.acc += ch[i];
      this.count += 1;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const s = Math.max(-1, Math.min(1, this.acc / this.count));
        this.acc = 0;
        this.count = 0;
        this.energy += s * s;
        this.frame[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        if (this.n === this.frame.length) {
          const level = Math.sqrt(this.energy / this.n);
          this.port.postMessage({ pcm: this.frame.buffer, level }, [this.frame.buffer]);
          this.frame = new Int16Array(1600);
          this.n = 0;
          this.energy = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("pcm-worklet", PcmWorklet);
