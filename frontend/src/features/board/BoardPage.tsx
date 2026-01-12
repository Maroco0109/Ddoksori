import { useState } from 'react';
import { Search, ThumbsUp, Calendar, Eye, MessageSquare } from 'lucide-react';
import { CATEGORY_DISPLAY_MAP, CATEGORY_LABELS, POST_CATEGORIES } from '@/shared/config/categories';
import type { BoardCategoryId, BoardPost, BoardPostForm, BoardSearchType } from './board.types';
import WritePost from './components/WritePost';
import PostDetail from './components/PostDetail';
import EditPost from './components/EditPost';

export default function BoardPage() {
  const [activeTab, setActiveTab] = useState<BoardCategoryId>('all');
  const [currentView, setCurrentView] = useState<'list' | 'write' | 'detail' | 'edit'>('list'); // 'list', 'write', 'detail', 'edit'
  const [selectedPost, setSelectedPost] = useState<BoardPost | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchType, setSearchType] = useState<BoardSearchType>('title'); // 'title', 'author', 'content', 'title_content'

  // 사이드바에서 자유게시판 클릭 시 목록으로 리셋

  // 카테고리를 첫 번째 "/"를 기준으로 2줄로 나누는 함수
  const splitCategory = (category: string) => {
    const firstSlashIndex = category.indexOf('/');
    if (firstSlashIndex === -1) return [category];
    return [
      category.substring(0, firstSlashIndex),
      category.substring(firstSlashIndex + 1)
    ];
  };

  // 작성자 표시 함수 (탈퇴한 사용자 처리)
  const getAuthorDisplayName = (author: string | undefined, isDeleted = false) => {
    if (isDeleted || !author) {
      return '탈퇴한 사용자';
    }
    return author;
  };

  const [posts, setPosts] = useState<BoardPost[]>([
    {
      id: 1,
      category: '분쟁해결사례/공유',
      title: '당근마켓 사기 피해 복구 성공했습니다',
      author: '김**',
      date: '2025.12.20',
      views: 234,
      likes: 45,
      comments: 12,
      preview: '입금 후 연락 두절된 판매자를 신고하고 계좌 지급정지 신청했더니...'
    },
    {
      id: 2,
      category: '분쟁해결사례/공유',
      title: '쿠팡 배송 파손 제품, 이렇게 해결했어요',
      author: '이**',
      date: '2025.12.19',
      views: 189,
      likes: 32,
      comments: 8,
      preview: '노트북이 파손되어 도착했는데 처음엔 환불 거부당했습니다. 하지만...'
    },
    {
      id: 3,
      category: '소비자/꿀팁/노하우',
      title: '소비자분쟁 조정 신청할 때 꼭 알아야 할 3가지',
      author: '박**',
      date: '2025.12.18',
      views: 456,
      likes: 78,
      comments: 23,
      preview: '여러 번 조정 신청 경험이 있는 사람으로서 초보자들에게 팁을 드립니다...'
    },
    {
      id: 4,
      category: '무엇이든/물어보세요',
      title: '환불 절차가 궁금합니다',
      author: '최**',
      date: '2025.12.17',
      views: 567,
      likes: 89,
      comments: 34,
      preview: '온라인 쇼핑몰에서 제품을 구매했는데 환불 절차가 복잡해서요...'
    },
    {
      id: 5,
      category: '분쟁해결사례/공유',
      title: '11번가 미배송 건 환불 성공 후기',
      author: '정**',
      date: '2025.12.16',
      views: 342,
      likes: 56,
      comments: 15,
      preview: '주문한 상품이 한 달째 배송되지 않아 소비자원에 신청했습니다...'
    },
    {
      id: 6,
      category: '소비자/꿀팁/노하우',
      title: '전자제품 AS 받을 때 꼭 챙겨야 할 것들',
      author: '한**',
      date: '2025.12.15',
      views: 523,
      likes: 92,
      comments: 28,
      preview: '보증기간 내 AS를 받을 때 놓치기 쉬운 포인트들을 정리해봤어요...'
    },
    {
      id: 7,
      category: '무엇이든/물어보세요',
      title: '중고거래 사기 당했는데 어떻게 해야 할까요?',
      author: '오**',
      date: '2025.12.14',
      views: 678,
      likes: 45,
      comments: 42,
      preview: '중고나라에서 거래했는데 계좌이체 후 연락이 안 됩니다...'
    },
    {
      id: 8,
      category: '분쟁해결사례/공유',
      title: '통신사 위약금 분쟁 해결 과정 공유',
      author: '강**',
      date: '2025.12.13',
      views: 412,
      likes: 67,
      comments: 19,
      preview: '약정 위반이라며 과도한 위약금을 청구받았는데 조정 신청으로...'
    },
    {
      id: 9,
      category: '소비자/꿀팁/노하우',
      title: '온라인 쇼핑 환불 거부 대처법',
      author: '윤**',
      date: '2025.12.12',
      views: 789,
      likes: 134,
      comments: 51,
      preview: '단순 변심 환불을 거부당했을 때 알아야 할 전자상거래법...'
    },
    {
      id: 10,
      category: '무엇이든/물어보세요',
      title: '택배 분실 시 보상 받는 방법 알려주세요',
      author: '임**',
      date: '2025.12.11',
      views: 445,
      likes: 38,
      comments: 26,
      preview: '고가의 물건을 보냈는데 택배가 분실되었다고 합니다...'
    },
    {
      id: 11,
      category: '분쟁해결사례/공유',
      title: '호텔 예약 취소 수수료 환불 받았어요',
      author: '서**',
      date: '2025.12.10',
      views: 356,
      likes: 48,
      comments: 14,
      preview: '천재지변으로 예약을 취소했는데 전액 수수료를 청구받아서...'
    },
    {
      id: 12,
      category: '소비자/꿀팁/노하우',
      title: '항공권 환불 최대한 받아내는 꿀팁',
      author: '신**',
      date: '2025.12.09',
      views: 891,
      likes: 156,
      comments: 63,
      preview: '코로나 이후 항공권 환불 정책이 많이 바뀌었는데요...'
    },
    {
      id: 13,
      category: '무엇이든/물어보세요',
      title: '헬스장 환불 문제 어떻게 해결하나요?',
      author: '권**',
      date: '2025.12.08',
      views: 623,
      likes: 71,
      comments: 38,
      preview: '이사로 인해 헬스장 환불을 요청했는데 거부당했습니다...'
    },
    {
      id: 14,
      category: '분쟁해결사례/공유',
      title: '자동차 중고거래 하자 분쟁 해결 후기',
      author: '송**',
      date: '2025.12.07',
      views: 534,
      likes: 82,
      comments: 29,
      preview: '중고차를 구입했는데 숨겨진 사고 이력이 있어서 분쟁조정을...'
    },
    {
      id: 15,
      category: '소비자/꿀팁/노하우',
      title: '신용카드 부정사용 피해 예방법',
      author: '유**',
      date: '2025.12.06',
      views: 712,
      likes: 98,
      comments: 44,
      preview: '카드 정보 유출로 피해를 입지 않으려면 이것만은 꼭...'
    },
    {
      id: 16,
      category: '무엇이든/물어보세요',
      title: '배달앱 환불 거부 정당한가요?',
      author: '조**',
      date: '2025.12.05',
      views: 489,
      likes: 54,
      comments: 32,
      preview: '음식이 상한 상태로 배달되었는데 환불이 안 된다고...'
    },
    {
      id: 17,
      category: '분쟁해결사례/공유',
      title: '가구 배송 파손 보상 받은 경험',
      author: '장**',
      date: '2025.12.04',
      views: 398,
      likes: 61,
      comments: 18,
      preview: '침대 프레임이 파손되어 배송되었는데 업체에서 책임 회피를...'
    },
    {
      id: 18,
      category: '소비자/꿀팁/노하우',
      title: '인터넷 쇼핑 피해 예방 체크리스트',
      author: '최**',
      date: '2025.12.03',
      views: 645,
      likes: 107,
      comments: 41,
      preview: '온라인 쇼핑 전 반드시 확인해야 할 사항들을 정리했습니다...'
    },
    {
      id: 19,
      category: '무엇이든/물어보세요',
      title: '렌탈 중도 해지 위약금이 너무 비싼데요',
      author: '안**',
      date: '2025.12.02',
      views: 556,
      likes: 69,
      comments: 35,
      preview: '정수기 렌탈을 중도 해지하려는데 위약금이 과도한 것 같아요...'
    },
    {
      id: 20,
      category: '분쟁해결사례/공유',
      title: '학원비 환불 100% 받아낸 방법',
      author: '황**',
      date: '2025.12.01',
      views: 723,
      likes: 128,
      comments: 52,
      preview: '학원법을 근거로 환불 요청했더니 전액 환불 받았습니다...'
    },
    {
      id: 21,
      category: '소비자/꿀팁/노하우',
      title: 'SNS 쇼핑몰 사기 피하는 법',
      author: '배**',
      date: '2025.11.30',
      views: 834,
      likes: 142,
      comments: 58,
      preview: '인스타그램 쇼핑몰에서 사기 당하지 않으려면...'
    },
    {
      id: 22,
      category: '무엇이든/물어보세요',
      title: '의료비 과다청구 신고 어떻게 하나요?',
      author: '노**',
      date: '2025.11.29',
      views: 467,
      likes: 53,
      comments: 27,
      preview: '병원에서 과도한 비급여 항목을 청구한 것 같은데...'
    },
    {
      id: 23,
      category: '분쟁해결사례/공유',
      title: '보험금 지급 거부 이의신청 성공',
      author: '문**',
      date: '2025.11.28',
      views: 592,
      likes: 87,
      comments: 31,
      preview: '보험사에서 보험금 지급을 거부했지만 금융감독원에 신청해서...'
    },
    {
      id: 24,
      category: '소비자/꿀팁/노하우',
      title: '청약철회 기간과 행사 방법 정리',
      author: '양**',
      date: '2025.11.27',
      views: 678,
      likes: 115,
      comments: 46,
      preview: '전자상거래법상 청약철회권에 대해 자세히 알아봅시다...'
    },
    {
      id: 25,
      category: '무엇이든/물어보세요',
      title: '중고차 보증 기간 내 고장, 어디에 요청하나요?',
      author: '전**',
      date: '2025.11.26',
      views: 523,
      likes: 64,
      comments: 29,
      preview: '중고차 매매 업체의 보증 기간이 있는데 고장이 났어요...'
    },
    {
      id: 26,
      category: '분쟁해결사례/공유',
      title: '항공사 수하물 분실 보상 받은 후기',
      author: '민**',
      date: '2025.11.25',
      views: 445,
      likes: 72,
      comments: 22,
      preview: '해외여행 중 수하물이 분실되어 항공사에 보상을 청구했습니다...'
    },
    {
      id: 27,
      category: '소비자/꿀팁/노하우',
      title: '명품 온라인 구매 시 주의사항',
      author: '차**',
      date: '2025.11.24',
      views: 756,
      likes: 103,
      comments: 39,
      preview: '명품 온라인 쇼핑 시 가품을 피하는 방법과 확인 포인트...'
    },
    {
      id: 28,
      category: '무엇이든/물어보세요',
      title: '세탁소 옷 분실, 배상 받을 수 있나요?',
      author: '주**',
      date: '2025.11.23',
      views: 389,
      likes: 47,
      comments: 24,
      preview: '세탁소에 맡긴 고가의 옷이 분실되었다는데 배상은...'
    },
    {
      id: 29,
      category: '분쟁해결사례/공유',
      title: '부동산 중개 수수료 분쟁 해결',
      author: '하**',
      date: '2025.11.22',
      views: 612,
      likes: 94,
      comments: 33,
      preview: '부동산 중개인이 과도한 수수료를 요구해서 분쟁조정을...'
    },
    {
      id: 30,
      category: '소비자/꿀팁/노하우',
      title: '구독 서비스 자동결제 해지하는 방법',
      author: '고**',
      date: '2025.11.21',
      views: 891,
      likes: 167,
      comments: 54,
      preview: 'OTT, 음악 스트리밍 등 구독 서비스 자동결제 관리 꿀팁...'
    }
  ]);

  const getCategoryDisplayName = (categoryId: BoardCategoryId) => {
    if (categoryId === 'all') {
      return CATEGORY_LABELS.all;
    }
    return CATEGORY_DISPLAY_MAP[categoryId];
  };

  const handleWritePost = (formData: BoardPostForm) => {
    const newPost = {
      id: Date.now(),
      category: getCategoryDisplayName(formData.category),
      title: formData.title,
      author: '현재사용자**',
      date: new Date().toLocaleDateString('ko-KR').replace(/\. /g, '.').slice(0, -1),
      views: 0,
      likes: 0,
      comments: 0,
      preview: formData.content.substring(0, 50) + (formData.content.length > 50 ? '...' : '')
    };
    setPosts([newPost, ...posts]);
    setSelectedPost(newPost); // 작성한 게시글 선택
    setCurrentView('detail'); // 상세 페이지로 이동
    // 스크롤 최상단으로 이동
    window.scrollTo(0, 0);
  };

  const handlePostClick = (post: BoardPost) => {
    setSelectedPost(post);
    setCurrentView('detail');
    // 스크롤 최상단으로 이동
    window.scrollTo(0, 0);
  };

  const handleEditPost = (post: BoardPost) => {
    setSelectedPost(post);
    setCurrentView('edit');
  };

  const handleUpdatePost = (postId: number, formData: BoardPostForm) => {
    const updatedPosts = posts.map(post => {
      if (post.id === postId) {
        const updatedPost = {
          ...post,
          category: getCategoryDisplayName(formData.category),
          title: formData.title,
          preview: formData.content.substring(0, 50) + (formData.content.length > 50 ? '...' : ''),
          editedDate: new Date().toLocaleDateString('ko-KR').replace(/\. /g, '.').slice(0, -1)
        };
        setSelectedPost(updatedPost); // 수정된 게시글로 selectedPost 업데이트
        return updatedPost;
      }
      return post;
    });
    setPosts(updatedPosts);
    setCurrentView('detail'); // 수정 후 상세 페이지로 이동
    // 스크롤 최상단으로 이동
    window.scrollTo(0, 0);
  };

  const handleDeletePost = (postId: number) => {
    setPosts(posts.filter(post => post.id !== postId));
    setCurrentView('list');
  };

  const categories: Array<{ id: BoardCategoryId; name: string }> = [
    { id: POST_CATEGORIES.ALL, name: CATEGORY_LABELS.all },
    { id: POST_CATEGORIES.CASE_SHARING, name: CATEGORY_LABELS['case-sharing'] },
    { id: POST_CATEGORIES.QNA, name: CATEGORY_LABELS.qna },
    { id: POST_CATEGORIES.TIPS, name: CATEGORY_LABELS.tips },
  ];

  // 페이지네이션 로직
  const getCategoryKey = (categoryId: BoardCategoryId) => {
    if (categoryId === 'all') {
      return CATEGORY_LABELS.all;
    }
    return CATEGORY_DISPLAY_MAP[categoryId];
  };

  // 카테고리별 필터링
  let filteredPosts = activeTab === 'all'
    ? posts
    : posts.filter(post => post.category === getCategoryKey(activeTab));

  // 검색 필터링
  if (searchQuery.trim()) {
    filteredPosts = filteredPosts.filter(post => {
      const query = searchQuery.toLowerCase();
      switch (searchType) {
        case 'title':
          return post.title.toLowerCase().includes(query);
        case 'author':
          return post.author.toLowerCase().includes(query);
        case 'content':
          return post.preview.toLowerCase().includes(query);
        case 'title_content':
          return post.title.toLowerCase().includes(query) || post.preview.toLowerCase().includes(query);
        default:
          return true;
      }
    });
  }

  // 총 페이지 수 계산
  const totalPages = Math.ceil(filteredPosts.length / itemsPerPage);

  // 현재 페이지에 표시할 게시글
  const indexOfLastPost = currentPage * itemsPerPage;
  const indexOfFirstPost = indexOfLastPost - itemsPerPage;
  const currentPosts = filteredPosts.slice(indexOfFirstPost, indexOfLastPost);

  // 페이지 번호 배열 생성 (최대 10개)
  const getPageNumbers = () => {
    const pageNumbers = [];
    const maxPagesToShow = 10;

    let startPage = Math.max(1, currentPage - Math.floor(maxPagesToShow / 2));
    let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);

    if (endPage - startPage < maxPagesToShow - 1) {
      startPage = Math.max(1, endPage - maxPagesToShow + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
      pageNumbers.push(i);
    }

    return pageNumbers;
  };

  // 페이지 변경 핸들러
  const handlePageChange = (pageNumber: number) => {
    setCurrentPage(pageNumber);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // 페이지당 표시 개수 변경 핸들러
  const handleItemsPerPageChange = (newItemsPerPage: number) => {
    // 현재 보고 있는 첫 번째 게시글의 인덱스 계산
    const currentFirstIndex = (currentPage - 1) * itemsPerPage;
    // 새로운 itemsPerPage에서 같은 위치가 속하는 페이지 계산
    const newPage = Math.floor(currentFirstIndex / newItemsPerPage) + 1;
    // 새로운 총 페이지 수 계산
    const newTotalPages = Math.ceil(filteredPosts.length / newItemsPerPage);
    // 새로운 페이지가 총 페이지 수를 초과하지 않도록 제한
    const validNewPage = Math.min(newPage, newTotalPages);

    setItemsPerPage(newItemsPerPage);
    setCurrentPage(validNewPage);
  };

  // 카테고리 변경 시 첫 페이지로 리셋
  const handleTabChange = (tabId: BoardCategoryId) => {
    setActiveTab(tabId);
    setCurrentPage(1);
  };

  // Conditional rendering based on current view
  if (currentView === 'write') {
    return (
      <WritePost
        onBack={() => setCurrentView('list')}
        onSubmit={handleWritePost}
      />
    );
  }

  if (currentView === 'edit' && selectedPost) {
    return (
      <EditPost
        post={selectedPost}
        onBack={() => setCurrentView('detail')}
        onSubmit={handleUpdatePost}
      />
    );
  }

  if (currentView === 'detail' && selectedPost) {
    return (
      <PostDetail
        post={selectedPost}
        onBack={() => setCurrentView('list')}
        onEdit={handleEditPost}
        onDelete={handleDeletePost}
      />
    );
  }

  return (
    <div className="board-page">
      {/* Board Header */}
      <div className="mb-6 md:mb-8">
        <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold mb-3 md:mb-4 text-dark-navy">자유게시판</h1>
        <p className="text-sm sm:text-base text-gray-purple">소비자 분쟁 경험을 공유하고 서로 도와요</p>
      </div>

      {/* Category Tabs */}
      <div className="flex gap-2 mb-4 md:mb-5 flex-wrap">
        {categories.map(cat => (
          <button
            key={cat.id}
            className={`px-4 sm:px-5 md:px-6 py-2 md:py-3 rounded-full text-sm md:text-base font-medium transition-all ${
              activeTab === cat.id
                ? 'bg-deep-teal text-white'
                : 'bg-white border-2 border-ivory text-gray-purple hover:border-lavender'
            }`}
            onClick={() => handleTabChange(cat.id)}
          >
            {cat.name}
          </button>
        ))}
      </div>

      {/* Write Button */}
      <div className="flex justify-end mb-6 md:mb-8">
        <button
          onClick={() => setCurrentView('write')}
          className="bg-deep-teal text-white px-6 sm:px-8 py-3 md:py-4 rounded-full text-sm sm:text-base font-semibold hover:bg-mint-green hover:-translate-y-1 transition-all whitespace-nowrap"
        >
          글쓰기
        </button>
      </div>

      {/* Search Bar */}
      <div className="flex items-center gap-3 md:gap-4 bg-white px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-full mb-4 md:mb-5 shadow-md">
        <Search size={18} className="text-gray-purple sm:w-5 sm:h-5" />
        <select
          value={searchType}
          onChange={(e) => setSearchType(e.target.value)}
          className="px-3 py-1.5 border-2 border-ivory rounded-lg text-sm font-medium text-gray-700 hover:border-lavender focus:outline-none focus:border-deep-teal transition-colors cursor-pointer"
        >
          <option value="title">제목</option>
          <option value="author">작성자</option>
          <option value="content">내용</option>
          <option value="title_content">제목+내용</option>
        </select>
        <input
          type="text"
          placeholder="게시글 검색..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 outline-none text-sm sm:text-base"
        />
      </div>

      {/* Items Per Page Selector & Info */}
      <div className="flex justify-between items-center mb-6 md:mb-8">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <span>전체 {filteredPosts.length}개</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">페이지당</span>
          <select
            value={itemsPerPage}
            onChange={(e) => handleItemsPerPageChange(Number(e.target.value))}
            className="px-3 py-1.5 border-2 border-ivory rounded-lg text-sm font-medium text-gray-700 hover:border-lavender focus:outline-none focus:border-deep-teal transition-colors cursor-pointer"
          >
            <option value={10}>10개</option>
            <option value={30}>30개</option>
            <option value={50}>50개</option>
          </select>
        </div>
      </div>

      {/* Posts - Mobile Card View */}
      <div className="xl:hidden flex flex-col gap-3">
        {currentPosts.map(post => (
          <div
            key={post.id}
            onClick={() => handlePostClick(post)}
            className="bg-white p-3 rounded-xl shadow-md hover:shadow-lg transition-all cursor-pointer"
          >
            <div className="flex items-start justify-between mb-2">
              <span className="inline-block px-2.5 py-1 bg-lavender/20 text-dark-navy rounded-full text-[11px] font-semibold whitespace-nowrap">
                {post.category.replace('/', ' ')}
              </span>
              <div className="flex items-center gap-1 text-[10px] text-gray-500">
                <Calendar size={10} />
                <span>{post.date}</span>
              </div>
            </div>

            <div className="group mb-2">
              <h3 className="text-sm font-bold text-dark-navy mb-1 hover:text-deep-teal transition-colors">
                {post.title}
              </h3>
              <p className="text-xs text-gray-500 line-clamp-2 hidden group-hover:block">{post.preview}</p>
            </div>

            <div className="flex items-center justify-between text-[10px] text-gray-600 pt-2 border-t border-gray-100">
              <span className="font-medium">{getAuthorDisplayName(post.author, post.isDeleted)}</span>
              <div className="flex items-center gap-2.5">
                <div className="flex items-center gap-0.5">
                  <Eye size={10} />
                  <span>{post.views}</span>
                </div>
                <div className="flex items-center gap-0.5">
                  <MessageSquare size={10} />
                  <span>{post.comments}</span>
                </div>
                <div className="flex items-center gap-0.5">
                  <ThumbsUp size={10} />
                  <span>{post.likes}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Posts - Desktop Table View */}
      <div className="hidden xl:block bg-white rounded-2xl shadow-md overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b-2 border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 w-32">카테고리</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">제목</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 w-28">날짜</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 w-24">작성자</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-gray-600 w-20">조회</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-gray-600 w-20">댓글</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-gray-600 w-20">좋아요</th>
              </tr>
            </thead>
            <tbody>
              {currentPosts.map(post => (
                <tr
                  key={post.id}
                  onClick={() => handlePostClick(post)}
                  className="border-b border-gray-100 hover:bg-lavender/10 transition-colors cursor-pointer"
                >
                  <td className="px-4 py-3">
                    <span className="inline-block px-2.5 py-1 bg-lavender/20 text-dark-navy rounded-full text-[11px] font-semibold text-center leading-relaxed">
                      {splitCategory(post.category).map((line, idx) => (
                        <span key={idx}>
                          {line}
                          {idx < splitCategory(post.category).length - 1 && <br />}
                        </span>
                      ))}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="group">
                      <h3 className="text-sm font-semibold text-dark-navy mb-0.5 hover:text-deep-teal transition-colors">
                        {post.title}
                      </h3>
                      <p className="text-xs text-gray-500 line-clamp-1 hidden group-hover:block">{post.preview}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 text-xs text-gray-600">
                      <Calendar size={12} />
                      <span>{post.date}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs font-medium text-gray-700">
                    {getAuthorDisplayName(post.author, post.isDeleted)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center gap-1 text-xs text-gray-600">
                      <Eye size={12} />
                      <span>{post.views}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center gap-1 text-xs text-gray-600">
                      <MessageSquare size={12} />
                      <span>{post.comments}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center gap-1 text-xs text-gray-600">
                      <ThumbsUp size={12} />
                      <span>{post.likes}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
          {/* Previous Button */}
          <button
            onClick={() => handlePageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className={`px-4 py-2 rounded-lg font-medium text-sm transition-all ${
              currentPage === 1
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-white border-2 border-ivory text-gray-700 hover:border-deep-teal hover:text-deep-teal'
            }`}
          >
            이전
          </button>

          {/* Page Numbers */}
          <div className="flex items-center gap-1 sm:gap-2 flex-wrap justify-center">
            {getPageNumbers().map(pageNumber => (
              <button
                key={pageNumber}
                onClick={() => handlePageChange(pageNumber)}
                className={`w-8 h-8 sm:w-10 sm:h-10 rounded-lg font-medium text-sm transition-all ${
                  currentPage === pageNumber
                    ? 'bg-deep-teal text-white'
                    : 'bg-white border-2 border-ivory text-gray-700 hover:border-deep-teal hover:text-deep-teal'
                }`}
              >
                {pageNumber}
              </button>
            ))}
          </div>

          {/* Next Button */}
          <button
            onClick={() => handlePageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            className={`px-4 py-2 rounded-lg font-medium text-sm transition-all ${
              currentPage === totalPages
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-white border-2 border-ivory text-gray-700 hover:border-deep-teal hover:text-deep-teal'
            }`}
          >
            다음
          </button>
        </div>
      )}
    </div>
  );
}
