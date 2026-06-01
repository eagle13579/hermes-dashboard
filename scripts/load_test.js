import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 10 },  // 10并发
    { duration: '30s', target: 50 },  // 升到50
    { duration: '30s', target: 0 },   // 降回0
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95%请求<500ms
    http_req_failed: ['rate<0.01'],   // 失败率<1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8090';

export default function () {
  // 1. Health
  let r1 = http.get(`${BASE_URL}/health`);
  check(r1, { 'health 200': (r) => r.status === 200 });

  // 2. Profiles list
  let r2 = http.get(`${BASE_URL}/api/profiles`);
  check(r2, { 'profiles 200': (r) => r.status === 200 });

  // 3. Kanban tasks
  let r3 = http.get(`${BASE_URL}/api/kanban`);
  check(r3, { 'kanban 200': (r) => r.status === 200 });

  // 4. Health history
  let r4 = http.get(`${BASE_URL}/api/health/history?hours=24`);
  check(r4, { 'health history 200': (r) => r.status === 200 });

  // 5. Auth login
  let r5 = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
    username: 'admin', password: 'admin123'
  }), { headers: { 'Content-Type': 'application/json' } });
  check(r5, { 'login 200': (r) => r.status === 200 });

  sleep(1);
}
