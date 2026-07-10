// Mantis-Bridge — Spicetify-Extension.
//
// Verbindet sich per WebSocket mit Mantis (/spicetify/ws) und beantwortet
// Kommandos über Spotifys interne APIs. Dadurch bekommt Mantis STRUKTURIERTE
// Daten (Suche/Track) direkt aus dem Client — ohne eigenen Developer-Key und
// ohne den blockierten Accessibility-Baum.
//
// Installation:
//   cp mantis-bridge.js ~/.config/spicetify/Extensions/
//   spicetify config extensions mantis-bridge.js
//   spicetify apply
//
// (Läuft im Spotify-Client; verbindet nur nach 127.0.0.1, keine externen Hosts.)

(function MantisBridge() {
  const URL = "ws://127.0.0.1:7779/spicetify/ws";
  const RECONNECT_MS = 5000;

  // Warten bis Spicetify bereit ist.
  if (!window.Spicetify || !Spicetify.Player || !Spicetify.CosmosAsync) {
    setTimeout(MantisBridge, 500);
    return;
  }

  function bestHit(json, preferred) {
    const order = preferred ? [preferred] : ["track", "album", "playlist", "artist"];
    for (const kind of order) {
      const items = (json[kind + "s"] && json[kind + "s"].items) || [];
      for (const it of items) {
        if (it && it.uri) {
          let name = it.name || "?";
          if (kind === "track" && it.artists && it.artists.length) {
            name += " — " + it.artists.map((a) => a.name).join(", ");
          }
          return { uri: it.uri, name };
        }
      }
    }
    return null;
  }

  async function handle(method, params) {
    const P = Spicetify.Player;
    switch (method) {
      case "search": {
        const q = encodeURIComponent(params.query || "");
        const types = params.typ || "track,album,playlist,artist";
        const url =
          "https://api.spotify.com/v1/search?q=" + q +
          "&type=" + types + "&limit=3&market=from_token";
        const json = await Spicetify.CosmosAsync.get(url);
        return bestHit(json, params.typ);
      }
      case "now_playing": {
        const d = P.data || {};
        const item = d.item || (d.track && d.track) || {};
        if (!item.uri) return null;
        const artists = (item.artists || []).map((a) => a.name).join(", ");
        return {
          title: item.name || item.title || "",
          artist: artists,
          album: (item.album && item.album.name) || "",
          playing: !(d.isPaused === true),
        };
      }
      case "play":
        await P.playUri(params.uri);
        return { ok: true };
      case "pause":
        P.pause();
        return { ok: true };
      case "resume":
        P.play();
        return { ok: true };
      case "next":
        P.next();
        return { ok: true };
      case "previous":
        P.back();
        return { ok: true };
      default:
        throw new Error("unbekannte Methode: " + method);
    }
  }

  let ws;
  function connect() {
    ws = new WebSocket(URL);
    ws.onmessage = async (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch (e) {
        return;
      }
      try {
        const result = await handle(msg.method, msg.params || {});
        ws.send(JSON.stringify({ id: msg.id, result }));
      } catch (e) {
        ws.send(JSON.stringify({ id: msg.id, error: String(e && e.message ? e.message : e) }));
      }
    };
    ws.onclose = () => setTimeout(connect, RECONNECT_MS);
    ws.onerror = () => ws.close();
  }
  connect();
})();
