/**
 * VIBE-FASHION 프론트엔드 자바스크립트 모듈
 */

/**
 * 하단 토스트 알림창을 띄우는 함수
 * @param {string} message - 화면에 표시할 메시지
 */
function showToast(message) {
    const toastEl = document.getElementById('actionToast');
    const toastBody = document.getElementById('toastMessage');
    
    if (toastEl && toastBody) {
        toastBody.innerText = message;
        const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
        toast.show();
    }
}

/**
 * 상단 네비게이션 뱃지(장바구니 / 관심 상품) 카운트 갱신
 */
function updateBadges(cartCount, wishlistCount) {
    const cartBadge = document.getElementById('cart-badge');
    if (cartBadge && cartCount !== undefined) {
        cartBadge.innerText = cartCount;
        cartBadge.classList.add('animate__animated', 'animate__pulse');
    }

    const wishBadge = document.getElementById('wishlist-badge');
    if (wishBadge && wishlistCount !== undefined) {
        wishBadge.innerText = wishlistCount;
        if (wishlistCount > 0) {
            wishBadge.classList.remove('d-none');
        } else {
            wishBadge.classList.add('d-none');
        }
    }
}

/**
 * 페이지 로드 시 최신 카운트 동기화
 */
document.addEventListener('DOMContentLoaded', () => {
    fetch('/api/counts')
        .then(res => res.json())
        .then(data => {
            updateBadges(data.cart_count, data.wishlist_count);
        })
        .catch(() => {});
});

/**
 * 장바구니 항목 삭제 (모달 표시)
 */
function removeFromCart(cartId) {
    window.pendingCartDeleteId = cartId;
    const deleteModal = new bootstrap.Modal(document.getElementById('deleteCartModal'));
    deleteModal.show();
}

/**
 * 모달에서 삭제 확인 버튼 클릭
 */
function confirmCartDelete() {
    const cartId = window.pendingCartDeleteId;
    if (!cartId) return;
    
    // 삭제 버튼 비활성화
    const confirmBtn = document.getElementById('confirmDeleteBtn');
    const originalText = confirmBtn.textContent;
    confirmBtn.disabled = true;
    confirmBtn.textContent = '삭제 중...';
    
    fetch(`/cart/${cartId}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            // Modal 닫기
            const modalEl = document.getElementById('deleteCartModal');
            const modalInstance = bootstrap.Modal.getInstance(modalEl);
            if (modalInstance) {
                modalInstance.hide();
            }
            
            // 해당 row 제거
            const cartRow = document.getElementById(`cart-row-${cartId}`);
            if (cartRow) {
                // fade out 효과
                cartRow.style.opacity = '0';
                cartRow.style.transition = 'opacity 0.3s';
                setTimeout(() => cartRow.remove(), 300);
            }
            
            // 토스트 메시지 표시
            showToast('상품이 장바구니에서 삭제되었습니다');
            
            // 장바구니가 비었는지 확인
            setTimeout(() => {
                const tableBody = document.querySelector('table tbody');
                if (!tableBody || tableBody.querySelectorAll('tr').length === 0) {
                    // 페이지 새로고침 (빈 상태 UI로 변경)
                    location.reload();
                }
            }, 500);
        } else {
            showToast(data.error || '삭제 중 오류가 발생했습니다');
            // 버튼 복구
            confirmBtn.disabled = false;
            confirmBtn.textContent = originalText;
        }
    })
    .catch(err => {
        console.error(err);
        showToast('삭제 중 오류가 발생했습니다');
        // 버튼 복구
        confirmBtn.disabled = false;
        confirmBtn.textContent = originalText;
    });
}

/**
 * 장바구니 전체 비우기 모달 표시
 */
function clearCart() {
    const modalEl = document.getElementById('clearCartModal');
    if (modalEl) {
        new bootstrap.Modal(modalEl).show();
    }
}

/**
 * 모달에서 장바구니 전체 삭제 확인
 */
function confirmClearCart() {
    // 삭제 버튼 비활성화
    const confirmBtn = document.getElementById('confirmClearBtn');
    const originalText = confirmBtn.textContent;
    confirmBtn.disabled = true;
    confirmBtn.textContent = '삭제 중...';
    
    fetch('/cart', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            // Modal 닫기
            const modalEl = document.getElementById('clearCartModal');
            const modalInstance = bootstrap.Modal.getInstance(modalEl);
            if (modalInstance) {
                modalInstance.hide();
            }
            
            // 토스트 메시지 표시
            showToast('장바구니가 비워졌습니다');
            
            // 페이지 새로고침
            setTimeout(() => {
                location.reload();
            }, 500);
        } else {
            showToast(data.error || '삭제 중 오류가 발생했습니다');
            // 버튼 복구
            confirmBtn.disabled = false;
            confirmBtn.textContent = originalText;
        }
    })
    .catch(err => {
        console.error(err);
        showToast('삭제 중 오류가 발생했습니다');
        // 버튼 복구
        confirmBtn.disabled = false;
        confirmBtn.textContent = originalText;
    });
}

/**
 * 상세 페이지 사이즈 옵션 선택 핸들러
 */
function selectProductOption(optionValue, btnElement) {
    const input = document.getElementById('selected-option-input');
    const label = document.getElementById('selected-option-label');
    if (input) input.value = optionValue;
    if (label) label.innerText = optionValue;

    const container = document.getElementById('size-options-container');
    if (container) {
        const buttons = container.querySelectorAll('.size-select-btn');
        buttons.forEach(b => {
            b.classList.remove('active', 'bg-dark', 'text-white');
            b.classList.add('btn-outline-dark');
        });
    }

    if (btnElement) {
        btnElement.classList.add('active', 'bg-dark', 'text-white');
        btnElement.classList.remove('btn-outline-dark');
    }
}

/**
 * 상세 페이지에서 선택된 사이즈 옵션과 함께 장바구니 담기
 */
function addCurrentDetailToCart(productId, productName, price, thumbnailUrl) {
    const input = document.getElementById('selected-option-input');
    const option = input ? input.value : 'FREE';
    addToCartAction(productId, productName, price, thumbnailUrl, option);
}

/**
 * 장바구니 추가 액션 (서버 API 연동)
 */
function addToCartAction(productId, productName, price, thumbnailUrl, option = 'FREE') {
    fetch('/api/cart/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            product_id: productId,
            name: productName,
            price: price,
            thumbnail_url: thumbnailUrl,
            option: option,
            quantity: 1
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            updateBadges(data.cart_count);
            showToast(`🛒 [${productName}] 상품이 장바구니에 담겼습니다!`);
        }
    })
    .catch(err => {
        console.error(err);
        showToast('장바구니 담기에 실패했습니다.');
    });
}

/**
 * 하위 호환성용 addToCart
 */
function addToCart(productName) {
    addToCartAction('', productName, 0, '');
}

/**
 * 관심 상품(위시리스트) 토글 액션 (서버 API 연동)
 */
function toggleWishlistAction(productId, productName, price, thumbnailUrl, btnElement = null) {
    fetch('/api/wishlist/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            product_id: productId,
            name: productName,
            price: price,
            thumbnail_url: thumbnailUrl
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            updateBadges(undefined, data.wishlist_count);
            showToast(data.message);

            if (btnElement) {
                const icon = btnElement.querySelector('i');
                if (data.is_active) {
                    btnElement.classList.add('active');
                    if (icon) icon.className = 'bi bi-heart-fill text-danger';
                } else {
                    btnElement.classList.remove('active');
                    if (icon) icon.className = 'bi bi-heart';
                }
            }

            // 위시리스트 페이지에서 바로 삭제된 경우 DOM 제거
            const rowCol = document.getElementById(`wishlist-col-${productId}`);
            if (rowCol && !data.is_active) {
                rowCol.remove();
                if (data.wishlist_count === 0) {
                    location.reload();
                }
            }
        }
    })
    .catch(err => {
        console.error(err);
        showToast('관심 상품 처리에 실패했습니다.');
    });
}

/**
 * 장바구니 수량 증감
 */
function updateCartQuantity(id, action) {
    fetch('/api/cart/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: id, action: action })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            location.reload();
        }
    });
}

/**
 * 장바구니 항목 삭제 (모달로 확인)
 */
function removeFromCart(cartId) {
    // Modal에서 삭제할 cart_id 저장
    window.pendingCartDeleteId = cartId;
    
    // Modal 열기
    const deleteModal = new bootstrap.Modal(document.getElementById('deleteCartModal'));
    deleteModal.show();
}

/**
 * 장바구니 전체 비우기
 */
function clearCart() {
    if (!confirm('장바구니를 모두 비우시겠습니까?')) return;
    fetch('/api/cart/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            location.reload();
        }
    });
}

/**
 * 위시리스트 페이지에서 장바구니 담고 바로 이동/안내
 */
function addCartAndRefresh(productId, productName, price, thumbnailUrl) {
    addToCartAction(productId, productName, price, thumbnailUrl);
}

/**
 * 카테고리 필터링 함수 (ALL, OUTER, TOP, BOTTOM)
 * @param {string} category - 선택된 카테고리
 * @param {HTMLElement} btnElement - 클릭된 버튼 엘리먼트
 */
function filterCategory(category, btnElement) {
    // 버튼 활성화 스타일 전환
    const buttons = btnElement.parentElement.querySelectorAll('button');
    buttons.forEach(b => {
        b.classList.remove('btn-dark', 'active');
        b.classList.add('btn-outline-dark');
    });
    btnElement.classList.remove('btn-outline-dark');
    btnElement.classList.add('btn-dark', 'active');

    // 카테고리 매핑 테이블 (영문 필터 키 -> 한글 카테고리명 매칭)
    const categoryMapping = {
        'ALL': ['ALL'],
        'TOP': ['상의', 'TOP'],
        'BOTTOM': ['하의', 'BOTTOM'],
        'OUTER': ['아우터', 'OUTER'],
        'SHOES': ['신발', 'SHOES'],
        'ACC': ['액세서리', 'ACC', '모자']
    };

    const targetList = categoryMapping[category] || [category];

    // 상품 카드 필터링
    const items = document.querySelectorAll('.product-item');
    items.forEach(item => {
        const itemCategory = (item.getAttribute('data-category') || '').trim();
        if (category === 'ALL' || targetList.includes(itemCategory)) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}
