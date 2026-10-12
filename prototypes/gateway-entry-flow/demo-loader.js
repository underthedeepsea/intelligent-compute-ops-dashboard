// Optional local samples. An ordinary checkout opens an empty editable directory.
window.GatewayDemoReady = fetch('demo-samples.json', {cache: 'no-store'})
  .then(response => {
    if (!response.ok) return;
    return response.json().then(data => GatewayDirectoryCore.setSamples(data));
  }).catch(() => {});
