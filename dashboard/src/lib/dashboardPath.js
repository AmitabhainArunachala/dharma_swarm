/**
 * @param {string | null | undefined} path
 * @returns {string | null}
 */
function normalizeDashboardPath(path) {
  if (!path) return null;
  if (path.length > 1 && path.endsWith("/")) {
    return path.slice(0, -1);
  }
  return path;
}

/**
 * @param {string} href
 * @param {string | null | undefined} currentPath
 * @returns {boolean}
 */
export function isDashboardPathActive(href, currentPath) {
  const normalizedHref = normalizeDashboardPath(href);
  const normalizedCurrentPath = normalizeDashboardPath(currentPath);

  if (!normalizedHref || !normalizedCurrentPath) {
    return false;
  }

  if (normalizedCurrentPath === normalizedHref) {
    return true;
  }

  if (normalizedHref === "/dashboard") {
    return false;
  }

  return normalizedCurrentPath.startsWith(`${normalizedHref}/`);
}
