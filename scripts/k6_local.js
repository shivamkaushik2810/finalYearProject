import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = (__ENV.BASE_URL || 'http://127.0.0.1:8501')
  .replace(/\/+$/, '');

const profiles = {
  smoke: [
    { duration: '10s', target: 1 },
    { duration: '10s', target: 2 },
    { duration: '10s', target: 5 },
  ],

  baseline: [
    { duration: '15s', target: 5 },
    { duration: '30s', target: 10 },
    { duration: '15s', target: 0 },
  ],

  load: [
    { duration: '30s', target: 10 },
    { duration: '60s', target: 25 },
    { duration: '60s', target: 50 },
    { duration: '30s', target: 0 },
  ],
};

const profile = __ENV.PROFILE || 'smoke';

export const options = {
  stages: profiles[profile] || profiles.smoke,

  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<5000'],
    checks: ['rate>0.95'],
  },

  userAgent: 'SnapClass-k6-performance-test/1.0',
};

export default function () {
  const response = http.get(`${BASE_URL}/`, {
    headers: {
      Accept: 'text/html',
    },
    timeout: '30s',
    tags: {
      endpoint: 'streamlit_home',
    },
  });

  check(response, {
    'homepage returns HTTP 200': (r) => r.status === 200,
    'homepage returns response body': (r) => !!r.body && r.body.length > 0,
    'response time below 5 seconds': (r) => r.timings.duration < 5000,
  });

  sleep(1);
}
