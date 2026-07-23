(() => {
  const header = document.querySelector('[data-header]');
  const toggle = document.querySelector('.menu-toggle');
  const navigation = document.getElementById('primary-navigation');
  const year = document.getElementById('current-year');

  if (year) {
    year.textContent = String(new Date().getFullYear());
  }

  if (header && toggle && navigation) {
    const closeMenu = (returnFocus = false) => {
      header.classList.remove('menu-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', '주 메뉴 열기');
      if (returnFocus) toggle.focus();
    };

    const openMenu = () => {
      header.classList.add('menu-open');
      toggle.setAttribute('aria-expanded', 'true');
      toggle.setAttribute('aria-label', '주 메뉴 닫기');
    };

    toggle.addEventListener('click', () => {
      toggle.getAttribute('aria-expanded') === 'true' ? closeMenu() : openMenu();
    });

    navigation.addEventListener('click', (event) => {
      if (event.target.closest('a')) closeMenu();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
        closeMenu(true);
      }
    });

    document.addEventListener('click', (event) => {
      if (
        toggle.getAttribute('aria-expanded') === 'true' &&
        !header.contains(event.target)
      ) {
        closeMenu();
      }
    });

    window.addEventListener('resize', () => {
      if (window.matchMedia('(min-width: 64rem)').matches) closeMenu();
    });
  }

  const shareButton = document.querySelector('[data-share]');
  const copyButton = document.querySelector('[data-copy-link]');
  const shareFeedback = document.querySelector('[data-share-feedback]');

  if (!shareButton && !copyButton) return;

  const canonicalUrl =
    document.querySelector('link[rel="canonical"]')?.href || window.location.href;
  const description =
    document.querySelector('meta[name="description"]')?.content || '';
  const shareData = {
    title: document.title,
    text: description,
    url: canonicalUrl,
  };

  const setFeedback = (message) => {
    if (shareFeedback) shareFeedback.textContent = message;
  };

  const copyWithFallback = async (text) => {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch {
        // 브라우저가 클립보드 권한을 제한하면 아래의 호환 복사 방식으로 전환합니다.
      }
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand('copy');
    textarea.remove();
    return copied;
  };

  const copyLink = async () => {
    try {
      const copied = await copyWithFallback(canonicalUrl);
      setFeedback(
        copied
          ? '글 주소를 복사했습니다.'
          : '주소를 복사하지 못했습니다. 브라우저 주소창에서 복사해 주세요.',
      );
    } catch {
      setFeedback('주소를 복사하지 못했습니다. 브라우저 주소창에서 복사해 주세요.');
    }
  };

  shareButton?.addEventListener('click', async () => {
    if (!navigator.share) {
      await copyLink();
      return;
    }

    try {
      await navigator.share(shareData);
      setFeedback('공유창을 열었습니다.');
    } catch (error) {
      if (error?.name !== 'AbortError') {
        setFeedback('공유창을 열지 못했습니다. 링크 복사를 이용해 주세요.');
      }
    }
  });

  copyButton?.addEventListener('click', copyLink);
})();
