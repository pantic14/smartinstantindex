export default function Help() {
  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">Help</h1>

      <div className="space-y-6">

        {/* ① Getting started */}
        <Card title="① Getting started">
          <ol className="list-decimal list-inside space-y-3 text-sm" style={{ color: "var(--color-muted)" }}>
            <li>
              <strong className="text-white">Upload credentials</strong> — Go to{" "}
              <strong className="text-white">Settings</strong> and upload your Google service account
              JSON file. See section ② below for how to create one.
            </li>
            <li>
              <strong className="text-white">Add a site</strong> — Click{" "}
              <strong className="text-white">New site</strong> on the Sites page. Enter a name,
              your sitemap URL, and assign the credentials you just uploaded.
            </li>
            <li>
              <strong className="text-white">Fetch URLs</strong> — Open the site and click{" "}
              <strong className="text-white">Fetch URLs</strong>. This reads your sitemap and
              populates the URL list.
            </li>
            <li>
              <strong className="text-white">Run Indexing</strong> — Click{" "}
              <strong className="text-white">▶ Run Indexing</strong>. SmartInstantIndex submits
              pending URLs to Google up to the daily quota (200 per GCP project).
            </li>
          </ol>
        </Card>

        {/* ② Google credentials */}
        <Card title="② Google credentials — step by step">
          <div className="text-sm space-y-4" style={{ color: "var(--color-muted)" }}>
            <Step n="1" title="Create a Google Cloud project">
              Go to{" "}
              <strong className="text-white">https://console.cloud.google.com</strong>, click the
              project selector at the top → <em>New Project</em>, give it a name and click{" "}
              <em>Create</em>.
            </Step>

            <Step n="2" title="Enable the Web Search Indexing API">
              In the search bar type <em>Web Search Indexing API</em>. Make sure the project you
              just created appears in the square at the top left — if not, click it and select it.
              Then click the API → <strong className="text-white">ENABLE</strong>.
            </Step>

            <Step n="3" title="Create a service account and download its key">
              <p>Click the menu → <em>IAM &amp; Admin</em> → <em>Service Accounts</em> → <em>+ Create Service Account</em>.</p>
              <p className="mt-1">Enter any name → <em>Create and Continue</em> → <em>Done</em>.</p>
              <p className="mt-1">Click the account you just created → <em>Keys</em> tab → <em>Add Key</em> → <em>Create new key</em> → JSON → <em>Create</em>.</p>
              <p className="mt-1">A <code className="text-xs" style={{ color: "#e6edf3" }}>.json</code> file is downloaded. Keep it safe — you will upload it in Settings.</p>
            </Step>

            <Step n="4" title="Add the service account to Google Search Console">
              <p>Copy the service account email (looks like{" "}
                <code className="text-xs" style={{ color: "#e6edf3" }}>name@project.iam.gserviceaccount.com</code>).
              </p>
              <p className="mt-1">Go to{" "}
                <strong className="text-white">https://search.google.com/search-console</strong>,
                select your property → <em>Settings</em> → <em>Users and permissions</em> →{" "}
                <em>Add user</em> → paste the email → set role to <strong className="text-white">Owner</strong> → Add.
              </p>
            </Step>

            <Step n="5" title="Upload the key in SmartInstantIndex">
              Go to <strong className="text-white">Settings</strong> → upload the JSON file.
              Then open your site → <em>Edit</em> → assign those credentials.
            </Step>

            <div
              className="rounded-lg p-3 mt-2 border"
              style={{ background: "rgba(255,255,255,0.03)", borderColor: "var(--color-rim)" }}
            >
              <p className="font-medium text-white mb-2">Optional — Enable "Sync from GSC"</p>
              <p className="mb-2">
                This feature checks which URLs Google has confirmed as indexed in Search Console
                and marks them automatically. It requires one extra step:
              </p>
              <p className="mb-1">
                1. In Google Cloud Console, also enable the{" "}
                <strong className="text-white">Google Search Console API</strong> (same steps as
                above, search for <em>Google Search Console API</em>).
              </p>
              <p className="mb-2">
                2. In your site settings, fill in the{" "}
                <strong className="text-white">Search Console Property URL</strong>. The value must
                match exactly how your site appears in Search Console:
              </p>
              <ul className="space-y-1 ml-2">
                <li>
                  <strong className="text-white">Domain property</strong> →{" "}
                  <code className="text-xs" style={{ color: "#e6edf3" }}>sc-domain:example.com</code>{" "}
                  <span>(verified via DNS — most common)</span>
                </li>
                <li>
                  <strong className="text-white">URL-prefix property</strong> →{" "}
                  <code className="text-xs" style={{ color: "#e6edf3" }}>https://example.com/</code>{" "}
                  <span>(verified via HTML file or meta tag)</span>
                </li>
              </ul>
              <p className="mt-2">
                To check your type: open Search Console and look at the property list on the left —
                domain properties show a globe icon, URL-prefix properties show a link icon.
              </p>
            </div>
          </div>
        </Card>

        {/* ③ Site detail & dashboard */}
        <Card title="③ Site detail">
          <div className="text-sm space-y-3" style={{ color: "var(--color-muted)" }}>
            <p>Open a site from the Sites page to see its full detail panel.</p>

            <p className="font-medium text-white">Stats cards</p>
            <ul className="space-y-1 ml-2">
              <li><strong className="text-white">Total URLs</strong> — number of URLs found in your sitemap.</li>
              <li><strong className="text-white">Sent to Google</strong> — URLs already submitted to the Indexing API.</li>
              <li><strong className="text-white">Indexed in GSC</strong> — URLs confirmed as indexed by Google Search Console (updated by Sync from GSC).</li>
              <li><strong className="text-white">Pending</strong> — URLs not yet submitted; they will be sent on the next run.</li>
            </ul>

            <p className="font-medium text-white mt-2">Quota bars</p>
            <p>
              If you have multiple credentials assigned, a progress bar appears for each one showing
              how many of its 200 daily URLs have been used today.
            </p>

            <p className="font-medium text-white mt-2">Actions</p>
            <ul className="space-y-2 ml-2">
              <li>
                <strong className="text-white">▶ Run Indexing</strong> — fetches the sitemap,
                syncs new/removed URLs, resets URLs whose lastmod changed (if Track lastmod is on),
                then submits pending URLs to Google up to the daily quota. The log panel shows
                real-time progress.
              </li>
              <li>
                <strong className="text-white">Fetch URLs</strong> — reads your sitemap and updates
                the URL list without submitting anything to Google. Use this to preview what has
                changed before running indexing.
              </li>
              <li>
                <strong className="text-white">Sync from GSC</strong> — queries Google Search
                Console for all confirmed-indexed pages and marks matching URLs with the GSC badge.
                Requires the Search Console Property URL to be set in the site's settings.
              </li>
            </ul>
          </div>
        </Card>

        {/* ④ URLs table */}
        <Card title="④ URLs table">
          <div className="text-sm space-y-3" style={{ color: "var(--color-muted)" }}>
            <p>The URLs table shows every page found in your sitemap and its current state.</p>

            <p className="font-medium text-white">Columns</p>
            <ul className="space-y-1 ml-2">
              <li><strong className="text-white">Status</strong> — <span style={{ color: "var(--color-accent-hover)" }}>sent</span> (submitted to Google) or <span style={{ color: "var(--color-warn)" }}>pending</span> (not yet submitted).</li>
              <li><strong className="text-white">Sent at</strong> — date when the URL was last submitted to the Indexing API.</li>
              <li><strong className="text-white">Lastmod</strong> — last-modified date reported by the sitemap. When Track lastmod is on and this date changes, the URL is automatically reset to pending.</li>
              <li><strong className="text-white">GSC</strong> — <span style={{ color: "var(--color-success)" }}>indexed</span> means Google Search Console has confirmed this URL is indexed. A dash means not yet synced or not found.</li>
            </ul>

            <p className="font-medium text-white mt-2">Filter tabs</p>
            <p>Use the <em>All</em> / <em>Pending</em> / <em>Indexed</em> tabs to narrow the list.</p>

            <p className="font-medium text-white mt-2">Bulk actions</p>
            <ul className="space-y-2 ml-2">
              <li>
                <strong className="text-white">Reset all</strong> — marks every URL as pending.
                Use this to force Google to re-index everything from scratch.
              </li>
              <li>
                <strong className="text-white">Reset selected</strong> — select one or more rows
                using the checkboxes, then click this to mark only those URLs as pending. They will
                be resubmitted on the next run.
              </li>
              <li>
                <strong className="text-white">Mark sent</strong> — manually marks selected URLs as
                sent (without actually submitting them). Useful if you know Google already has them
                and want to skip re-submission.
              </li>
            </ul>
          </div>
        </Card>

        {/* ⑤ Filters & settings */}
        <Card title="⑤ Filters & settings">
          <div className="text-sm space-y-3" style={{ color: "var(--color-muted)" }}>
            <p>
              Filters are configured per site. Open the site → click{" "}
              <strong className="text-white">Edit</strong>.
            </p>

            <ul className="space-y-3 ml-2">
              <li>
                <strong className="text-white">Track lastmod</strong> (on/off) — when on, if your
                sitemap reports a new <code className="text-xs" style={{ color: "#e6edf3" }}>lastmod</code>{" "}
                date for a URL, that URL is automatically reset to pending on the next run. Useful
                for blogs or sites that update content frequently.
              </li>
              <li>
                <strong className="text-white">Skip extensions</strong> — file types to ignore
                completely (one per line). URLs ending with these extensions are excluded before
                anything else is checked. Default list includes images, PDFs, videos and archives:
                <code className="text-xs block mt-1 ml-2" style={{ color: "#e6edf3" }}>
                  .jpg .jpeg .png .gif .webp .svg .pdf .mp4 .zip
                </code>
              </li>
              <li>
                <strong className="text-white">Exclude patterns</strong> — regular expressions
                (or plain strings). If a URL matches any exclude pattern it is ignored. Example:
                adding{" "}
                <code className="text-xs" style={{ color: "#e6edf3" }}>/tag/</code> skips all tag
                pages. Exclude always takes priority over Include.
              </li>
              <li>
                <strong className="text-white">Include patterns</strong> — if this list is{" "}
                <em>not empty</em>, only URLs matching at least one pattern are processed; all
                others are ignored. Example: adding{" "}
                <code className="text-xs" style={{ color: "#e6edf3" }}>/blog/</code> processes only
                blog posts.
              </li>
            </ul>
          </div>
        </Card>

        {/* ⑥ Multiplying daily quota */}
        <Card title="⑥ Multiplying the daily quota">
          <div className="text-sm space-y-3" style={{ color: "var(--color-muted)" }}>
            <p>
              Google's limit of <strong className="text-white">200 URLs/day</strong> is per GCP{" "}
              <em>project</em>, not per service account. By assigning credentials from multiple
              different GCP projects to the same site, SmartInstantIndex automatically rotates to
              the next credential when the current one hits its daily limit.
            </p>
            <p>
              <strong className="text-white">Example:</strong> 3 credentials from 3 different
              projects → 600 URLs/day for the same site.
            </p>

            <p className="font-medium text-white mt-1">How to set it up</p>
            <p>Repeat these steps for each additional GCP project you want to add:</p>

            <ol className="list-decimal list-inside space-y-3 ml-2 mt-2">
              <li>
                <strong className="text-white">Create a new GCP project</strong> — go to
                Google Cloud Console → project selector → <em>New Project</em>.
              </li>
              <li>
                <strong className="text-white">Enable the Web Search Indexing API</strong> — search
                for <em>Web Search Indexing API</em>, make sure the new project is selected, click{" "}
                <em>ENABLE</em>.
              </li>
              <li>
                <strong className="text-white">Create a service account and download its key</strong>{" "}
                — IAM &amp; Admin → Service Accounts → <em>+ Create</em> → name it → Keys tab →
                Add Key → JSON → Create. Save the downloaded{" "}
                <code className="text-xs" style={{ color: "#e6edf3" }}>.json</code> file.
              </li>
              <li>
                <strong className="text-white">Add the service account to Search Console</strong>{" "}
                — copy its email, go to Search Console → your property → Settings → Users and
                permissions → Add user → paste email → Owner → Add. You can add multiple service
                accounts to the same property.
              </li>
              <li>
                <strong className="text-white">Upload and assign in SmartInstantIndex</strong> —
                go to <em>Settings</em> and upload the new JSON file, then open your site →{" "}
                <em>Edit</em> → add the new credentials. Click <em>Save</em>.
              </li>
            </ol>

            <p className="mt-1">
              The site detail page shows a quota bar per credential so you can see how much each
              one has used today.
            </p>
          </div>
        </Card>

        {/* Open source */}
        <Card title="Open source">
          <p className="text-sm" style={{ color: "var(--color-muted)" }}>
            SmartInstantIndex is open source software. The core indexing logic and this local web
            app are free to use, modify, and share.{" "}
            <strong className="text-white">
              Need scheduled automatic indexing, multi-site management, and more?
            </strong>{" "}
            Check out SmartInstantIndex Cloud.
          </p>
        </Card>

      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded-xl border p-5"
      style={{ background: "var(--color-navy-card)", borderColor: "var(--color-rim)" }}
    >
      <h2 className="font-semibold mb-3">{title}</h2>
      {children}
    </div>
  );
}

function Step({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="font-medium text-white mb-1">
        Step {n} — {title}
      </p>
      <div style={{ color: "var(--color-muted)" }}>{children}</div>
    </div>
  );
}
