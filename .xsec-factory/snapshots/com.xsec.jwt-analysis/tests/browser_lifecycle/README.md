# JWT frontend lifecycle regression

The browser checks use the real frontend module, browser DOM and timers, HTTP,
and the plugin's SQLite Store and report functions. The loopback component
connector provides read-only JWT queries for two isolated projects. Desktop
authorization, native plugin installation, and MCP transport require separate
Host acceptance.

The five cases cover project updates, disposal after mount, disposal during a
pending mount, a project update during a pending mount, and a failed refresh.
The failure case renames the isolated database's jobs table temporarily, so
the HTTP response contains a real SQLite error. A completed observation window
checks that disposal and refresh failure stop subsequent polling.

Each case runs in a separate browser iframe, which releases the baseline's
leaked timers when the case ends. The baseline file is the committed frontend
from `f159dcda672e03a19516f7741c1dfa139a466c9b`; all five cases fail on that
revision and pass with the lifecycle change. The controller still propagates
actual request failures. A user refresh starts a new explicit attempt.

Run through the workspace's build resource controller. Its Python command is:

```sh
rtk python3 tests/browser_lifecycle/serve.py \
  --root /absolute/path/to/xsec-plugin-jwt-analysis \
  --data /Volumes/xsec-build/evidence/jwt-lifecycle/sqlite \
  --baseline /Volumes/xsec-build/evidence/jwt-lifecycle/baseline.js \
  --evidence /Volumes/xsec-build/evidence/jwt-lifecycle
```

Prepare `baseline.js` using `git show` for the exact revision above and create
the evidence directory before running. Open the printed loopback URL in a real
browser and click the run button once. The server records `browser-results.json`
and exits when every case finishes. Save a screenshot of the final page.
An incomplete case has a 20-second deadline; failed cases remain visible in
the result and are not rerun automatically.
