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

  function nameOf(d) {
    let n = d.name || (d.profile && d.profile.name) || "";
    const arts = d.artists && d.artists.items;
    if (arts && arts.length) {
      n += " — " + arts.map((a) => (a.profile && a.profile.name) || a.name || "")
        .filter(Boolean).join(", ");
    }
    return n || "?";
  }

  function _itemData(it) {
    return (it && it.item && it.item.data) || (it && it.data) || it;
  }

  // Gezielter Parser auf die searchV2-Trefferlisten. Bevorzugt Tracks, dann
  // Album/Playlist/Artist, dann Top-Result. `typ` erzwingt eine Kategorie.
  function pickBest(data, typ) {
    const s = data && (data.searchV2 || data.search || data.searchModalResults || data);
    if (!s) return null;
    const buckets = {
      track: s.tracksV2 && s.tracksV2.items,
      album: (s.albumsV2 || s.albums) && (s.albumsV2 || s.albums).items,
      playlist: (s.playlistsV2 || s.playlists) && (s.playlistsV2 || s.playlists).items,
      artist: (s.artistsV2 || s.artists) && (s.artistsV2 || s.artists).items,
    };
    const order = typ ? [typ] : ["track", "album", "playlist", "artist"];
    for (const kind of order) {
      for (const it of buckets[kind] || []) {
        const d = _itemData(it);
        if (d && d.uri) return { uri: d.uri, name: nameOf(d) };
      }
    }
    const top = s.topResults && (s.topResults.itemsV2 || s.topResults.items);
    for (const it of top || []) {
      const d = _itemData(it);
      if (d && d.uri) return { uri: d.uri, name: nameOf(d) };
    }
    return null;
  }

  async function handle(method, params) {
    const P = Spicetify.Player;
    switch (method) {
      case "search": {
        // Interne GraphQL-Suche (externe fetch()->api.spotify.com wird vom Client
        // geblockt: code 429 'Failed to fetch').
        const GQL = Spicetify.GraphQL;
        if (!GQL || !GQL.Definitions) throw new Error("Spicetify.GraphQL fehlt");
        const def = GQL && GQL.Definitions &&
          (GQL.Definitions.searchModalResults || GQL.Definitions.searchDesktop);
        // Ohne Definition oder bei Fehler: als "nicht verfügbar" werfen → Mantis
        // fällt sauber auf den Web-API-Weg zurück (statt Fehler-Spam).
        if (!def) throw new Error("Client-Suche nicht verfügbar");
        let res;
        try {
          res = await GQL.Request(def, {
            searchTerm: params.query || "", offset: 0, limit: 8, numberOfTopResults: 5,
          });
        } catch (e) {
          throw new Error("Client-Suche nicht verfügbar (GraphQL)");
        }
        return pickBest(res && res.data, params.typ);  // null = kein Treffer
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
