// Surfaces: appear only where the spotlight (or a base stipple level) covers them, decided per
// pixel by an ordered 4x4 Bayer dither. cover=1 never discards, cover=0 always does, so the
// spotlight edge dissolves into a fine halftone instead of a soft alpha blur. Surfaces write
// depth, so inside the spotlight hidden lines are occluded (a built house); outside it every
// line shows (a blueprint).

export const SURFACE_VERT = /* glsl */ `
varying vec3 vN;
varying vec3 vW;
void main() {
  vec4 w = modelMatrix * vec4(position, 1.0);
  vW = w.xyz;
  vN = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * viewMatrix * w;
}
`

export const SURFACE_FRAG = /* glsl */ `
precision highp float;
uniform vec2  uMouse;   // device px, origin bottom-left (gl_FragCoord space)
uniform float uRadius;  // device px
uniform float uBase;    // 0..1 baseline stipple everywhere
uniform float uFade;
uniform float uKind;    // 0 plain, 1 planks, 2 tile, 3 mosaic, 4 decking
uniform float uDark;    // 0 light theme, 1 dark theme
varying vec3 vN;
varying vec3 vW;

const float B[16] = float[16](0.,8.,2.,10., 12.,4.,14.,6., 3.,11.,1.,9., 15.,7.,13.,5.);

float pattern(vec2 p, float kind) {
  float line = 0.0;
  if (kind > 0.5 && kind < 1.5) {
    float row = floor(p.y / 0.19);
    line = smoothstep(0.46, 0.5, abs(fract(p.y / 0.19) - 0.5));
    float lc = abs(fract(p.x / 1.3 + fract(row * 0.37)) - 0.5);
    line = max(line, smoothstep(0.494, 0.5, lc));
  } else if (kind < 2.5 && kind > 1.5) {
    vec2 g = abs(fract(p / 0.6) - 0.5);
    line = smoothstep(0.485, 0.5, max(g.x, g.y));
  } else if (kind < 3.5 && kind > 2.5) {
    vec2 g = abs(fract(p / 0.12) - 0.5);
    line = smoothstep(0.455, 0.5, max(g.x, g.y));
  } else if (kind > 3.5) {
    line = smoothstep(0.43, 0.5, abs(fract(p.y / 0.14) - 0.5));
  }
  // fade the pattern out when it gets sub-pixel, instead of letting it shimmer
  float aa = (fwidth(p.x) + fwidth(p.y));
  return line * (1.0 - smoothstep(0.04, 0.16, aa));
}

void main() {
  float d = distance(gl_FragCoord.xy, uMouse);
  float spot = 1.0 - smoothstep(uRadius * 0.38, uRadius, d);
  float cover = max(spot, uBase) * uFade;
  int bi = int(mod(gl_FragCoord.x, 4.0)) + int(mod(gl_FragCoord.y, 4.0)) * 4;
  if (cover < (B[bi] + 0.5) / 16.0) discard;

  vec3 n = normalize(vN);
  float lam = dot(n, normalize(vec3(0.45, 0.85, 0.30))) * 0.5 + 0.5;
  vec3 col = mix(vec3(0.80), vec3(0.975), lam);
  col *= mix(0.9, 1.0, smoothstep(0.0, 1.4, vW.y));
  float up = step(0.85, n.y);
  col = mix(col, vec3(0.56), pattern(vW.xz, uKind) * up * 0.6);
  // dark theme: the same shading on near-black, floor pattern lifted instead of darkened
  vec3 dcol = mix(vec3(0.07), vec3(0.19), lam);
  dcol *= mix(0.85, 1.0, smoothstep(0.0, 1.4, vW.y));
  dcol = mix(dcol, vec3(0.36), pattern(vW.xz, uKind) * up * 0.7);
  col = mix(col, dcol, uDark);
  gl_FragColor = vec4(col, 1.0);
}
`

export const LINE_VERT = /* glsl */ `
void main() {
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`

export const LINE_FRAG = /* glsl */ `
precision highp float;
uniform vec2  uMouse;
uniform float uRadius;
uniform float uLo;    // line opacity outside the spotlight (blueprint)
uniform float uHi;    // inside the spotlight (built)
uniform float uHot;   // 0..1 emphasis (focused room or layer)
uniform float uFade;
uniform float uDark;
void main() {
  float d = distance(gl_FragCoord.xy, uMouse);
  float spot = 1.0 - smoothstep(uRadius * 0.38, uRadius, d);
  float a = mix(uLo, uHi, spot);
  a = mix(a, 1.0, uHot * 0.85);
  gl_FragColor = vec4(vec3(mix(0.035, 0.94, uDark)), a * uFade);
}
`
