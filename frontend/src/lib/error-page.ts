export function renderErrorPage(): string {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>This page didn't load</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font: 15px/1.5 'DM Sans', Inter, system-ui, sans-serif; background: #080A08; color: #F9F9F9; display: grid; place-items: center; min-height: 100vh; margin: 0; padding: 1.5rem; }
      .card { max-width: 28rem; width: 100%; text-align: center; padding: 2rem; background: #111411; border: 1px solid #30382C; border-radius: 10px; }
      h1 { font-size: 1.25rem; margin: 0 0 0.5rem; color: #F9F9F9; }
      p { color: #A3A4A1; margin: 0 0 1.5rem; }
      .actions { display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; }
      a, button { padding: 0.5rem 1rem; border-radius: 0.5rem; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; text-decoration: none; border: 1px solid transparent; transition: all 150ms ease; }
      .primary { background: #A7FE08; color: #10130A; font-weight: 700; box-shadow: 0 0 16px rgba(167, 254, 8, 0.2); }
      .primary:hover { background: #BBFF45; }
      .secondary { background: #151A14; color: #F9F9F9; border-color: #30382C; }
      .secondary:hover { background: #1A2018; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>This page didn't load</h1>
      <p>Something went wrong on our end. You can try refreshing or head back home.</p>
      <div class="actions">
        <button class="primary" onclick="location.reload()">Try again</button>
        <a class="secondary" href="/">Go home</a>
      </div>
    </div>
  </body>
</html>`;
}
