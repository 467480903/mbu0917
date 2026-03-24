let lastTimestamp = 0;

export function nextTimestamp() {
  const now = Math.max(Date.now(), lastTimestamp + 1);
  lastTimestamp = now;
  const date = new Date(now);
  const two = value => String(value).padStart(2, '0');
  return `${date.getFullYear()}${two(date.getMonth() + 1)}${two(date.getDate())}`
    + `${two(date.getHours())}${two(date.getMinutes())}${two(date.getSeconds())}`
    + String(date.getMilliseconds()).padStart(3, '0');
}
