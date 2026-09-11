import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import * as socialApi from "../api/social";

const PLATFORMS = [
  { key: "youtube", label: "YouTube", live: true },
  { key: "instagram", label: "Instagram", live: false },
];

const ERROR_MESSAGE = {
  invalid_state: "That connection attempt looked tampered with — please try again.",
  youtube_connect_failed: "Google didn't let us finish connecting. Please try again.",
  youtube_not_configured: "YouTube isn't configured on this server yet.",
};

export default function Connections() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();

  function refresh() {
    socialApi.listAccounts().then((a) => {
      setAccounts(a);
      setLoading(false);
    });
  }

  useEffect(refresh, []);

  // Captured once into state, not read live from searchParams — otherwise clearing the
  // query string below (so a page refresh doesn't re-show a stale banner) would erase
  // the very value the banner is rendering, in the same render pass.
  const [connectedMsg] = useState(() => searchParams.get("connected"));
  const [errorCode] = useState(() => searchParams.get("error"));

  useEffect(() => {
    if (connectedMsg || errorCode) {
      const next = new URLSearchParams(searchParams);
      next.delete("connected");
      next.delete("error");
      setSearchParams(next, { replace: true });
    }
    // Only meant to run once, on arrival from the OAuth redirect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function disconnect(id) {
    await socialApi.disconnectAccount(id);
    refresh();
  }

  if (loading) return null;

  const byPlatform = Object.fromEntries(accounts.map((a) => [a.platform, a]));

  return (
    <>
      <p className="eyebrow">Settings</p>
      <h1 className="page-title">Connections</h1>
      <p className="page-sub">Connect your own YouTube and Instagram accounts to publish approved stories to.</p>

      {connectedMsg && <div className="banner banner-success">Connected your {connectedMsg} account.</div>}
      {errorCode && <div className="banner banner-error">{ERROR_MESSAGE[errorCode] || "Something went wrong connecting that account."}</div>}

      <div className="connections-list">
        {PLATFORMS.map(({ key, label, live }) => {
          const account = byPlatform[key];
          return (
            <div className="create-panel connection-row" key={key}>
              <div>
                <div className="connection-platform">{label}</div>
                {account ? (
                  <div className="connection-detail">
                    Connected as <strong>{account.external_account_name}</strong>
                    {" — "}
                    {new Date(account.connected_at).toLocaleDateString()}
                  </div>
                ) : (
                  <div className="connection-detail">{live ? "Not connected." : "Coming soon."}</div>
                )}
              </div>
              {live && (
                account ? (
                  <button type="button" className="btn btn-danger-outline" onClick={() => disconnect(account.id)}>Disconnect</button>
                ) : (
                  <a className="btn btn-gold" href={socialApi.connectUrl(key)}>Connect</a>
                )
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
