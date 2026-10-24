export const TOPICS = Object.freeze({
  base: { request: '/humanoid/base/request/', response: '/humanoid/base/response/' },
  joint: { request: '/humanoid/joint/request/', response: '/humanoid/joint/response/' },
  pose: { request: '/humanoid/pose/request/', response: '/humanoid/pose/response/' },
  ee: { request: '/humanoid/ee/request/', response: '/humanoid/ee/response/' },
  tts: { request: '/humanoid/tts/request/', response: '/humanoid/tts/response/' },
  camera: { request: '/humanoid/camera/request/', response: '/humanoid/camera/response/' },
  apriltag: { request: '/humanoid/apriltag/request/', response: '/humanoid/apriltag/response/' },
  db: { request: '/humanoid/db/request/', response: '/humanoid/db/response/' },
  maptest: { request: '/humanoid/maptest/request/', response: '/humanoid/maptest/response/' },
  sync: { request: '/humanoid/sync/request/', response: '/humanoid/sync/response/', data: '/humanoid/sync/data/' },
  done: '/humanoid/done/',
});

export const responseTopics = () => [
  ...Object.values(TOPICS).flatMap(value => typeof value === 'object'
    ? [value.response, value.data].filter(Boolean) : []),
  TOPICS.done,
];
