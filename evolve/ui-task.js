// A newer selection or navigation invalidates an older asynchronous UI operation.
export function createLatestTask() {
  let generation = 0;
  return {
    begin() {
      const current = ++generation;
      return { isCurrent: () => current === generation };
    },
    cancel() {
      generation++;
    },
  };
}
