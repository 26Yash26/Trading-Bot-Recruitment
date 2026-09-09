// Google sign-in, restricted to @smail.iitm.ac.in.
//
// The OAuth round trip lands back on the server, which sets an HttpOnly cookie
// and redirects, no token ever passes through the URL or through JS.

import { navigate, store } from "../main.js";
import { revealLines } from "../motion.js";
import { esc, toast } from "../ui.js";

const DENIAL_REASONS = {
  domain: "That Google account is not an @smail.iitm.ac.in address.",
  unverified: "That Google account has no verified email address.",
  state: "The sign-in link expired. Please try again.",
  token: "Google did not return a valid token. Please try again.",
  nocode: "Google did not return an authorisation code. Please try again.",
};

const googleMark = `
  <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
    <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.2l6.7-6.7C35.7 2.3 30.2 0 24 0 14.7 0 6.7 5.5 2.9 13.5l7.8 6C12.5 13.3 17.8 9.5 24 9.5z"/>
    <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4 7.1-10 7.1-17z"/>
    <path fill="#FBBC05" d="M10.7 28.5A14.7 14.7 0 0 1 9.5 24c0-1.6.3-3.1.8-4.5l-7.8-6A23.9 23.9 0 0 0 0 24c0 3.9.9 7.5 2.5 10.8l8.2-6.3z"/>
    <path fill="#34A853" d="M24 48c6.2 0 11.4-2 15.2-5.5l-7.5-5.8c-2 1.4-4.6 2.3-7.7 2.3-6.2 0-11.5-4.2-13.3-9.8l-8.2 6.3C6.7 42.5 14.7 48 24 48z"/>
  </svg>`;

export async function renderLogin(app) {
  const params = new URLSearchParams(location.search);
  const auth = params.get("auth");
  const reason = params.get("reason") || "";

  if (auth) {
    history.replaceState({}, "", "/login");
    if (auth === "denied" || auth === "failed") {
      toast(DENIAL_REASONS[reason] || "Sign-in failed. Please try again.", "error", 8000);
    }
  }

  if (store.me.signed_in) {
    navigate("/submit", { replace: true });
    return;
  }

  const configured = store.me.oauth_configured !== false;

  app.innerHTML = `
    <section class="bleed grid min-h-[70vh] items-center gap-14 py-20 lg:grid-cols-2" data-reveal>
      <div class="max-w-lg">
        <span class="tag" data-fade>Sign in</span>
        <h1 class="d1 mt-8 font-display">${revealLines(["The board", "is open."])}</h1>
        <p class="lede mt-10" data-fade>
          Anyone can read the leaderboard and the problem statement. To upload a bot you need an
          <span class="font-mono text-flame">@smail.iitm.ac.in</span> account, because a submission
          has to be bound to a roll number that belongs to a real person.
        </p>
        <ul class="mt-10 space-y-4 text-sm text-ink-2" data-fade>
          <li class="flex gap-3"><span class="text-flame">▸</span>We read your name and email address, and nothing else.</li>
          <li class="flex gap-3"><span class="text-flame">▸</span>Your roll number is taken from the address, not typed in.</li>
          <li class="flex gap-3"><span class="text-flame">▸</span>The session is a cookie the page itself cannot read.</li>
        </ul>
      </div>

      <div class="panel p-8 lg:justify-self-end lg:w-full lg:max-w-md" data-fade>
        ${
          configured
            ? `<a href="/api/auth/login"
                  class="flex w-full items-center justify-center gap-3 border border-line-2 bg-white
                         px-5 py-4 font-mono text-[11px] uppercase tracking-[0.18em] text-[#1f2328]
                         transition-colors hover:border-flame">
                 ${googleMark} Continue with Google
               </a>`
            : `<div class="border-l-2 border-l-loss px-5 py-4 text-sm text-loss">
                 Google sign-in is not configured on this server yet. Set
                 <span class="font-mono text-xs">QG_GOOGLE_CLIENT_ID</span> and
                 <span class="font-mono text-xs">QG_GOOGLE_CLIENT_SECRET</span>.
               </div>`
        }

        <p class="hair mt-8 pt-6 font-mono text-[11px] leading-relaxed text-ink-3">
          Only the <span class="text-flame">smail.iitm.ac.in</span> domain is accepted. A personal
          Gmail address is turned away by Google before it ever reaches this site.
        </p>

        ${
          reason && auth === "denied"
            ? `<p class="mt-5 font-mono text-[11px] text-loss">${esc(
                DENIAL_REASONS[reason] || reason
              )}</p>`
            : ""
        }
      </div>
    </section>`;
}
