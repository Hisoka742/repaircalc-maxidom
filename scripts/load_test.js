// k6 equivalent of scripts/load_test.py (cold scenario): 200 req/s of unique room estimates.
//   k6 run scripts/load_test.js            (BASE_URL env var overrides the target)
// Thresholds encode the plan's targets: p95 < 50 ms, no 5xx.
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const TYPES = ['living', 'bedroom', 'kitchen', 'bathroom', 'kids', 'hallway'];
const CLASSES = ['cosmetic', 'major', 'designer'];

export const options = {
  scenarios: {
    estimates: {
      executor: 'constant-arrival-rate', rate: 200, timeUnit: '1s', duration: '10m',
      preAllocatedVUs: 50, maxVUs: 400,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<50'],
    http_req_failed: ['rate<0.001'],
  },
};

export default function () {
  const body = JSON.stringify({
    room: {
      length_m: (2 + Math.random() * 7).toFixed(3),
      width_m: (2 + Math.random() * 5).toFixed(3),
      height_m: '2.7',
    },
    room_type: TYPES[Math.floor(Math.random() * TYPES.length)],
    renovation_class: CLASSES[Math.floor(Math.random() * CLASSES.length)],
  });
  const res = http.post(`${BASE}/v1/calc/room`, body, { headers: { 'Content-Type': 'application/json' } });
  check(res, { 'status is 200': (r) => r.status === 200 });
}
