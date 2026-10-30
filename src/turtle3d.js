/* The Carve turtle model: a crafty turtle (grey cube, dark frame, chest / crafting-grid / slot faces). Shared by the 3D viewer and the Fleet map.
   It faces -Z. CarveTurtle.make(THREE, seed) gives every turtle its own hue (light pink, blue, mint...) with the same texture. */
var CarveTurtle = (function () {
  var FRAME = "#23252c", DARK = "#1b1d23";
  // a body colour per turtle; light, so the dark frame and icons stay readable
  var HUES = ["#f2b8d0", "#9fc4f2", "#a8e6c4", "#d2b8f2", "#f6cfa6", "#f2ec9c", "#92e0e0", "#f2a8a0", "#b8b8f4", "#c8e89c", "#e6b0e6", "#a8d8f6"];
  var cache = {};

  function hash(s) {
    var h = 0; s = String(s);
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return Math.abs(h);
  }
  function shade(hex, f) {
    var n = parseInt(hex.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
    function c(v) { return Math.max(0, Math.min(255, Math.round(v * f))); }
    return "rgb(" + c(r) + "," + c(g) + "," + c(b) + ")";
  }
  // one 16x16 face drawn as big pixels
  function face(THREE, tint, draw) {
    var cv = document.createElement("canvas"); cv.width = cv.height = 64;
    var x = cv.getContext("2d"), K = 4;
    function R(c, a, b, w, h) { x.fillStyle = c; x.fillRect(a * K, b * K, w * K, h * K); }
    R(FRAME, 0, 0, 16, 16);
    R(shade(tint, 0.82), 1, 1, 14, 14);
    R(shade(tint, 1.0), 2, 2, 12, 12);
    R(shade(tint, 1.1), 2, 2, 12, 1); R(shade(tint, 1.1), 2, 2, 1, 12);
    R(shade(tint, 0.88), 2, 13, 12, 1); R(shade(tint, 0.88), 13, 2, 1, 12);
    if (draw) draw(R);
    var t = new THREE.CanvasTexture(cv);
    t.magFilter = THREE.NearestFilter; t.minFilter = THREE.NearestFilter;
    return t;
  }
  function frameBox(R, a, b, w, h) {                         // an outlined rectangle
    R(DARK, a, b, w, 1); R(DARK, a, b + h - 1, w, 1); R(DARK, a, b, 1, h); R(DARK, a + w - 1, b, 1, h);
  }
  function icons(THREE, t) {
    return {
      top: face(THREE, t, null),
      right: face(THREE, t, null),
      bottom: face(THREE, t, function (R) {                    // four nested squares
        [[2, 2], [8, 2], [2, 8], [8, 8]].forEach(function (p) {
          frameBox(R, p[0], p[1], 6, 6); frameBox(R, p[0] + 1, p[1] + 1, 4, 4); R(DARK, p[0] + 2, p[1] + 2, 2, 2);
        });
      }),
      front: face(THREE, t, function (R) {                     // the turtle's face: a wide slot, a little checker and a plus
        R(DARK, 3, 3, 10, 2); R(shade(t, 0.7), 3, 5, 10, 1);
        R(shade(t, 0.9), 2, 6, 12, 7);                                           // the lower plate, a touch darker
        [[3, 7], [5, 7], [4, 8], [3, 9], [5, 9]].forEach(function (p) { R(shade(t, 0.6), p[0] + 0.25, p[1] + 0.25, 1, 1); R("#fbfbff", p[0], p[1], 1, 1); });
        [[7, 10], [6, 11], [7, 11], [8, 11], [7, 12]].forEach(function (p) { R(shade(t, 0.6), p[0] + 0.25, p[1] + 0.25, 1, 1); R("#fbfbff", p[0], p[1], 1, 1); });
      }),
      back: face(THREE, t, function (R) {                      // a chest and a little slot
        frameBox(R, 3, 3, 10, 8); R(DARK, 3, 6, 10, 1); R(DARK, 7, 5, 2, 3); R(DARK, 10, 12, 4, 2);
      }),
      left: face(THREE, t, function (R) {                      // the crafting grid
        frameBox(R, 3, 3, 10, 10); frameBox(R, 4, 4, 8, 8); R(DARK, 6, 4, 1, 8); R(DARK, 9, 4, 1, 8); R(DARK, 4, 6, 8, 1); R(DARK, 4, 9, 8, 1);
      })
    };
  }
  function build(THREE, tint, k) {
    var ic = cache[k] || (cache[k] = icons(THREE, tint)), g = new THREE.Group();
    function M(tex) { return new THREE.MeshLambertMaterial({ map: tex }); }
    g.add(new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.8, 0.8),
      [M(ic.right), M(ic.left), M(ic.top), M(ic.bottom), M(ic.back), M(ic.front)]));
    return g;
  }
  return {
    hash: hash,
    count: HUES.length,
    hues: HUES,
    variantOf: function (seed) { return (typeof seed === "number" ? Math.abs(seed) : hash(seed)) % HUES.length; },
    make: function (THREE, seed) {
      var k = this.variantOf(seed);
      var g = build(THREE, HUES[k], k);
      g.userData.variant = k;
      return g;
    }
  };
})();
