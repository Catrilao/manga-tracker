(() => {
  const card = document.querySelector("div.layout-container.manga");

  const titleNode = card ? card.querySelector("div.title p") : null;
  const name = titleNode?.textContent || '';

  const imgNode = card ? card.querySelector("div[style*='grid-area: art'] img[alt='Cover image']") : null;
  const thumbnail = imgNode?.getAttribute("src") || '';

  return {
    name,
    thumbnail
  };
})();
