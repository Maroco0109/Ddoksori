import type { AdminStats, AdminPost, AdminUser, Report } from '@/shared/types/admin';

// 통계 데이터
export const mockStats: AdminStats = {
  totalUsers: 1247,
  totalPosts: 3892,
  totalComments: 12456,
  pendingReports: 8,
  suspendedUsers: 3, // 정지(suspended) 2명 + 영구정지(banned) 1명
  todayNewUsers: 23,
  todayNewPosts: 67,
  todayNewComments: 142,
};

// 게시글 데이터
export const mockPosts: AdminPost[] = [
  {
    id: 1,
    category: '공지사항',
    title: '[긴급] 시스템 점검 안내',
    content: '안녕하세요. 관리자입니다.\n\n다음 주 화요일 오전 2시부터 4시까지 시스템 점검이 예정되어 있습니다.\n점검 시간 동안 서비스 이용이 제한될 수 있으니 양해 부탁드립니다.\n\n감사합니다.',
    author: '관리자',
    authorId: 'admin-1',
    createdAt: '2026-01-28T10:30:00Z',
    updatedAt: '2026-01-28T10:30:00Z',
    views: 1523,
    likes: 45,
    commentsCount: 12,
    isPublic: true,
    isDeleted: false,
  },
  {
    id: 2,
    category: '공지사항',
    title: '게시판 이용 규칙 안내',
    content: '게시판 이용 규칙:\n\n1. 욕설, 비방, 혐오 표현을 금지합니다.\n2. 음란물, 불법 정보 게시를 금지합니다.\n3. 동일 내용의 반복 게시 및 상업적 광고 행위는 허용되지 않습니다.\n4. 위반 시 게시물은 비공개 또는 삭제 처리될 수 있으며, 위반 정도에 따라 경고, 일정 기간 이용 제한, 또는 계정 이용 정지 조치가 적용될 수 있습니다.\n\n모두가 즐겁게 이용할 수 있는 커뮤니티를 만들어주세요.',
    author: '관리자',
    authorId: 'admin-1',
    createdAt: '2026-01-20T14:20:00Z',
    views: 2341,
    likes: 89,
    commentsCount: 34,
    isPublic: true,
    isDeleted: false,
  },
  {
    id: 3,
    category: '사례 공유',
    title: '이 게시글은 욕설이 포함되어 비공개 처리되었습니다',
    content: '부적절한 내용으로 인해 비공개 처리된 게시글입니다.',
    author: '김철수',
    authorId: 'user-001',
    createdAt: '2026-01-27T09:15:00Z',
    views: 234,
    likes: 3,
    commentsCount: 8,
    isPublic: false,
    isDeleted: false,
  },
  {
    id: 4,
    category: '사례 공유',
    title: '당근마켓 사기 피해 환불 받았어요!',
    content: '안녕하세요! 당근마켓에서 중고 노트북을 구매했는데 입금 후 연락이 두절되었습니다.\n\n해결 과정:\n1. 거래 내역 캡처 및 증거 수집\n2. 경찰서 사기 신고\n3. 은행에 지급정지 신청\n4. 소비자원 분쟁조정 신청\n\n결과적으로 전액 환불 받았습니다! 같은 피해 입으신 분들께 도움이 되길 바랍니다.',
    author: '박영희',
    authorId: 'user-002',
    createdAt: '2025-12-26T16:45:00Z',
    views: 892,
    likes: 67,
    commentsCount: 23,
    isPublic: true,
    isDeleted: false,
  },
  {
    id: 5,
    category: 'Q&A',
    title: '온라인 쇼핑몰 환불 거부 시 대처법 문의',
    content: '쿠팡에서 구매한 제품이 불량인데 환불을 거부당했습니다.\n\n소비자분쟁해결기준에 따르면 환불이 가능한 것 같은데, 어떻게 대응해야 할까요?\n경험 있으신 분들의 조언 부탁드립니다!',
    author: '이민수',
    authorId: 'user-003',
    createdAt: '2025-12-20T11:20:00Z',
    views: 567,
    likes: 34,
    commentsCount: 45,
    isPublic: true,
    isDeleted: false,
  },
  {
    id: 6,
    category: '팁',
    title: '소비자분쟁 조정 신청 꿀팁 정리',
    content: '여러 번 분쟁조정 경험이 있는 사람으로서 팁 공유합니다:\n\n1. 모든 거래 내역과 대화 기록 보관\n2. 제품 하자는 사진/영상으로 명확히 증거 확보\n3. 한국소비자원 1372 상담 먼저 받기\n4. 분쟁조정 신청서 작성 시 구체적으로 작성\n5. 관련 법령과 소비자분쟁해결기준 확인\n\n도움이 되셨으면 좋겠습니다!',
    author: '최지원',
    authorId: 'user-004',
    createdAt: '2025-12-15T13:30:00Z',
    views: 1456,
    likes: 123,
    commentsCount: 56,
    isPublic: true,
    isDeleted: false,
  },
  {
    id: 7,
    category: '사례 공유',
    title: '광고성 게시글입니다 - 삭제 예정',
    content: '○○○ 제품 구매하세요! 최저가 할인 중!\n지금 바로 구매하시면...',
    author: '스팸계정',
    authorId: 'user-008',
    createdAt: '2025-12-10T08:00:00Z',
    views: 12,
    likes: 0,
    commentsCount: 0,
    isPublic: false,
    isDeleted: false,
  },
  {
    id: 8,
    category: 'Q&A',
    title: '배송 지연 보상 받을 수 있나요?',
    content: '11번가에서 주문한 상품이 2주째 배송이 안 되고 있습니다.\n\n판매자는 택배사 문제라고 하는데, 배송 지연에 대한 보상을 요구할 수 있을까요?\n관련 법령이나 판례가 있는지 궁금합니다.',
    author: '정수진',
    authorId: 'user-005',
    createdAt: '2025-12-05T15:10:00Z',
    views: 723,
    likes: 56,
    commentsCount: 34,
    isPublic: true,
    isDeleted: false,
  },
];

// 회원 데이터
export const mockUsers: AdminUser[] = [
  {
    id: 'user-001',
    name: '김철수',
    email: 'kim.cs@gmail.com',
    provider: 'google',
    createdAt: '2025-12-15T09:30:00Z',
    lastLoginAt: '2026-01-28T14:20:00Z',
    status: 'active',
    postCount: 23,
    commentCount: 156,
    reportCount: 0,
  },
  {
    id: 'user-002',
    name: '박영희',
    email: 'park.yh@naver.com',
    provider: 'naver',
    createdAt: '2025-11-10T11:00:00Z',
    lastLoginAt: '2026-01-28T10:15:00Z',
    status: 'active',
    postCount: 45,
    commentCount: 234,
    reportCount: 0,
  },
  {
    id: 'user-003',
    name: '이민수',
    email: 'lee.ms@naver.com',
    provider: 'naver',
    createdAt: '2025-10-20T14:30:00Z',
    lastLoginAt: '2026-01-27T16:45:00Z',
    status: 'active',
    postCount: 12,
    commentCount: 89,
    reportCount: 0,
  },
  {
    id: 'user-004',
    name: '최지원',
    email: 'choi.jw@gmail.com',
    provider: 'google',
    createdAt: '2025-09-05T08:20:00Z',
    lastLoginAt: '2026-01-28T09:30:00Z',
    status: 'active',
    postCount: 67,
    commentCount: 423,
    reportCount: 0,
  },
  {
    id: 'user-005',
    name: '정수진',
    email: 'jung.sj@naver.com',
    provider: 'naver',
    createdAt: '2025-08-20T10:00:00Z',
    lastLoginAt: '2026-01-26T18:20:00Z',
    status: 'active',
    postCount: 89,
    commentCount: 567,
    reportCount: 1,
  },
  {
    id: 'user-006',
    name: '강민호',
    email: 'kang.mh@gmail.com',
    provider: 'google',
    createdAt: '2025-12-18T13:45:00Z',
    lastLoginAt: '2026-01-22T11:30:00Z',
    status: 'suspended',
    postCount: 8,
    commentCount: 34,
    reportCount: 3,
  },
  {
    id: 'user-007',
    name: '윤서연',
    email: 'yoon.sy@naver.com',
    provider: 'naver',
    createdAt: '2025-11-12T16:20:00Z',
    lastLoginAt: '2026-01-20T14:10:00Z',
    status: 'suspended',
    postCount: 5,
    commentCount: 12,
    reportCount: 5,
  },
  {
    id: 'user-008',
    name: '스팸계정',
    email: 'spam@test.com',
    provider: 'google',
    createdAt: '2025-12-25T07:00:00Z',
    lastLoginAt: '2025-12-25T08:30:00Z',
    status: 'banned',
    postCount: 15,
    commentCount: 3,
    reportCount: 12,
  },
  {
    id: 'user-009',
    name: '홍길동',
    email: 'hong.gd@naver.com',
    provider: 'naver',
    createdAt: '2025-07-15T09:00:00Z',
    lastLoginAt: '2026-01-28T15:30:00Z',
    status: 'active',
    postCount: 134,
    commentCount: 892,
    reportCount: 0,
  },
  {
    id: 'user-010',
    name: '신지훈',
    email: 'shin.jh@gmail.com',
    provider: 'google',
    createdAt: '2025-10-05T12:30:00Z',
    lastLoginAt: '2026-01-27T13:20:00Z',
    status: 'active',
    postCount: 34,
    commentCount: 178,
    reportCount: 0,
  },
];

// 신고 데이터
export const mockReports: Report[] = [
  {
    id: 1,
    type: 'post',
    targetId: 3,
    targetTitle: '이 게시글은 욕설이 포함되어 비공개 처리되었습니다',
    targetContent: '욕설과 비방이 포함된 내용입니다...',
    reporterId: 'user-002',
    reporterName: '박영희',
    reason: '욕설 및 비방 표현이 포함되어 있습니다.',
    createdAt: '2026-01-27T10:00:00Z',
    status: 'pending',
  },
  {
    id: 2,
    type: 'post',
    targetId: 7,
    targetTitle: '광고성 게시글입니다 - 삭제 예정',
    targetContent: '○○○ 제품 구매하세요! 최저가 할인 중!',
    reporterId: 'user-001',
    reporterName: '김철수',
    reason: '상업적 광고 게시물입니다.',
    createdAt: '2025-12-25T09:00:00Z',
    status: 'pending',
  },
  {
    id: 3,
    type: 'comment',
    targetId: 101,
    targetContent: '이런 쓰레기 같은 글을...',
    reporterId: 'user-004',
    reporterName: '최지원',
    reason: '댓글에 욕설이 포함되어 있습니다.',
    createdAt: '2026-01-26T14:30:00Z',
    status: 'pending',
  },
  {
    id: 4,
    type: 'post',
    targetId: 25,
    targetTitle: '쿠팡 환불 100% 받는 방법',
    targetContent: '사실과 다른 정보를 퍼뜨리는 게시글...',
    reporterId: 'user-005',
    reporterName: '정수진',
    reason: '허위 정보를 유포하고 있습니다.',
    createdAt: '2026-01-24T11:20:00Z',
    status: 'reviewed',
    adminNote: '내용 확인 중입니다.',
  },
  {
    id: 5,
    type: 'comment',
    targetId: 102,
    targetContent: '또 광고하네... 사기꾼들',
    reporterId: 'user-003',
    reporterName: '이민수',
    reason: '댓글로 광고를 반복하고 있습니다.',
    createdAt: '2025-12-23T16:45:00Z',
    status: 'resolved',
    adminNote: '해당 댓글 삭제 및 사용자 경고 조치 완료',
  },
  {
    id: 6,
    type: 'post',
    targetId: 30,
    targetTitle: '11번가 배송 지연 보상 후기',
    targetContent: '특별한 문제가 없는 정상적인 게시글입니다.',
    reporterId: 'user-010',
    reporterName: '신지훈',
    reason: '마음에 안 들어요',
    createdAt: '2025-12-22T10:00:00Z',
    status: 'rejected',
    adminNote: '신고 내용 확인 결과 위반 사항이 없어 기각 처리합니다.',
  },
  {
    id: 7,
    type: 'comment',
    targetId: 103,
    targetContent: '혐오 표현이 담긴 댓글...',
    reporterId: 'user-009',
    reporterName: '홍길동',
    reason: '특정 집단에 대한 혐오 표현이 있습니다.',
    createdAt: '2026-01-27T18:20:00Z',
    status: 'pending',
  },
  {
    id: 8,
    type: 'post',
    targetId: 35,
    targetTitle: '도배성 게시글',
    targetContent: '같은 내용을 계속 반복해서 올리고 있습니다.',
    reporterId: 'user-004',
    reporterName: '최지원',
    reason: '동일 내용을 반복적으로 게시하고 있습니다.',
    createdAt: '2026-01-28T09:15:00Z',
    status: 'pending',
  },
];

// Mock API 응답 함수
export const getMockData = (endpoint: string, params?: any): any => {
  // 통계
  if (endpoint === '/api/admin/stats') {
    return mockStats;
  }

  // 게시글 목록
  if (endpoint === '/api/admin/posts') {
    let filteredPosts = [...mockPosts];

    // 검색 필터 적용
    if (params?.searchKeyword) {
      const keyword = params.searchKeyword.toLowerCase();
      filteredPosts = filteredPosts.filter((post) => {
        if (params.searchType === 'title') {
          return post.title.toLowerCase().includes(keyword);
        } else if (params.searchType === 'author') {
          return post.author.toLowerCase().includes(keyword);
        } else if (params.searchType === 'title_author') {
          return (
            post.title.toLowerCase().includes(keyword) ||
            post.author.toLowerCase().includes(keyword)
          );
        } else {
          return (
            post.title.toLowerCase().includes(keyword) ||
            post.content.toLowerCase().includes(keyword)
          );
        }
      });
    }

    // 공개 상태 필터
    if (params?.isPublic !== undefined) {
      filteredPosts = filteredPosts.filter((post) => post.isPublic === params.isPublic);
    }

    return filteredPosts;
  }

  // 게시글 상세
  if (endpoint.startsWith('/api/admin/posts/') && !endpoint.includes('visibility') && !endpoint.includes('notice')) {
    const postId = parseInt(endpoint.split('/').pop() || '0');
    return mockPosts.find((post) => post.id === postId) || null;
  }

  // 회원 목록
  if (endpoint === '/api/admin/users') {
    let filteredUsers = [...mockUsers];

    // 검색 필터
    if (params?.searchKeyword) {
      const keyword = params.searchKeyword.toLowerCase();
      filteredUsers = filteredUsers.filter(
        (user) =>
          user.name.toLowerCase().includes(keyword) ||
          user.email.toLowerCase().includes(keyword)
      );
    }

    // 상태 필터
    if (params?.status) {
      filteredUsers = filteredUsers.filter((user) => user.status === params.status);
    }

    // 제공자 필터
    if (params?.provider) {
      filteredUsers = filteredUsers.filter((user) => user.provider === params.provider);
    }

    return filteredUsers;
  }

  // 회원 상세
  if (endpoint.startsWith('/api/admin/users/') && !endpoint.includes('status')) {
    const userId = endpoint.split('/').pop();
    return mockUsers.find((user) => user.id === userId) || null;
  }

  // 신고 목록
  if (endpoint === '/api/admin/reports') {
    let filteredReports = [...mockReports];

    // 유형 필터
    if (params?.type) {
      filteredReports = filteredReports.filter((report) => report.type === params.type);
    }

    // 상태 필터
    if (params?.status) {
      filteredReports = filteredReports.filter((report) => report.status === params.status);
    }

    return filteredReports;
  }

  // 신고 상세
  if (endpoint.startsWith('/api/admin/reports/') && !endpoint.includes('status')) {
    const reportId = parseInt(endpoint.split('/').pop() || '0');
    return mockReports.find((report) => report.id === reportId) || null;
  }

  return null;
};
