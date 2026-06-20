(() => {
  const chapters = document.querySelectorAll('div.chapter.relative');
  return Array.from(chapters).map(chapter => {
      const infoNode = chapter.querySelector('.line-clamp-1');

      const card = chapter.closest('.bg-accent');
      let headerText = '';
      if (card) {
          const headerNode = card.querySelector(".chapter-header .font-bold.self-center");
          if (headerNode) headerText = headerNode.textContent;
      }

      const anchorNode = chapter.querySelector('a[href]');
      let href = "";
      let language = "";
      if (anchorNode) {
        href = anchorNode.getAttribute('href') || '';
        const imgNode = anchorNode.querySelector('img');
        if (imgNode) language = imgNode.getAttribute('title') || '';
      }

      return {
        info_text: infoNode ? infoNode.textContent : '',
        header_text: headerText,
        href: href,
        language_title: language,
      };
  });
})();
