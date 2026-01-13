import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/shared/config/routes';
import { MessageCircle, FileText, MessageSquare } from 'lucide-react';
import { useChatStore } from '@/features/chat/chat.store';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import bell1 from '@/shared/assets/icons/bell_1.png';
import bell2 from '@/shared/assets/icons/bell_2.png';

gsap.registerPlugin(ScrollTrigger);

export default function HomePage() {
  const section1Ref = useRef<HTMLDivElement | null>(null);
  const section2Ref = useRef<HTMLDivElement | null>(null);
  const bellContainerRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();
  const startNewChat = useChatStore((state) => state.startNewChat);

  // Bell 인터랙션 상태
  const [isHappy, setIsHappy] = useState(false);
  const [petCount, setPetCount] = useState(0);
  const petThreshold = 10; // 10번 쓰다듬으면 웃는 얼굴로 변경
  const lastPetTime = useRef(0);
  const petDelay = 150; // 150ms 간격으로만 카운트 증가

  // 쓰다듬기 핸들러 (쓰로틀링 적용)
  const handlePet = () => {
    if (!isHappy) {
      const now = Date.now();
      if (now - lastPetTime.current >= petDelay) {
        lastPetTime.current = now;
        setPetCount((prev) => {
          const newCount = prev + 1;
          if (newCount >= petThreshold) {
            setIsHappy(true);
          }
          return newCount;
        });
      }
    }
  };

  // 마우스가 벗어나면 리셋
  const handleMouseLeave = () => {
    if (!isHappy) {
      setPetCount(0);
    }
  };

  useEffect(() => {
    // Lenis 스무스 스크롤 초기화
    const lenis = new Lenis({
      duration: 1.2,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
    });

    function raf(time) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }
    requestAnimationFrame(raf);

    // GSAP ScrollTrigger와 Lenis 연동
    lenis.on('scroll', ScrollTrigger.update);

    gsap.ticker.add((time) => {
      lenis.raf(time * 1000);
    });

    gsap.ticker.lagSmoothing(0);

    return () => {
      lenis.destroy();
      ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
    };
  }, []);

  return (
    <div className="main-page snap-y snap-mandatory bg-ivory">
      {/* 메인 히어로 섹션 */}
      <div
        ref={section1Ref}
        className="relative flex flex-col items-center justify-center bg-ivory pt-12 md:pt-20 pb-8 md:pb-12"
      >
        {/* 텍스트 콘텐츠 */}
        <div ref={section2Ref} className="text-center px-4 sm:px-6 md:px-8">
          <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold leading-tight mb-4 md:mb-6 text-dark-navy">
            <span className="text-deep-teal">똑</span>똑한 <span className="text-deep-teal">소</span>비자의 권<span className="text-deep-teal">리</span>,<br />
            <span className="text-deep-teal">똑소리</span>가 지켜드립니다
          </h1>
          <button
            className="inline-flex items-center gap-2 md:gap-3 bg-deep-teal text-white px-6 sm:px-8 md:px-12 py-3 sm:py-4 md:py-5 rounded-full text-sm sm:text-base md:text-lg font-semibold hover:bg-mint-green transform hover:-translate-y-1 transition-all shadow-lg shadow-deep-teal/40 hover:shadow-mint-green/50"
            onClick={() => {
              window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
              document.documentElement.scrollTop = 0;
              document.body.scrollTop = 0;
              startNewChat();
              navigate(ROUTES.CHAT);
            }}
          >
            <MessageCircle size={18} className="sm:w-5 sm:h-5" />
            무료 상담 시작하기
          </button>
        </div>
      </div>

      {/* Features Grid */}
      <div className="bg-ivory px-4 sm:px-6 md:px-8 pt-4 md:pt-8 pb-8 md:pb-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6 md:gap-8 max-w-6xl mx-auto">
          <div className="bg-white p-6 sm:p-8 md:p-10 rounded-2xl shadow-lg hover:shadow-2xl hover:-translate-y-2 transition-all">
            <div className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 bg-deep-teal rounded-2xl flex items-center justify-center mb-4 md:mb-6">
              <MessageCircle size={24} className="text-white sm:w-7 sm:h-7 md:w-8 md:h-8" />
            </div>
            <h3 className="text-lg sm:text-xl md:text-2xl font-bold mb-3 md:mb-4 text-dark-navy">AI 챗봇</h3>
            <p className="text-sm sm:text-base text-gray-purple leading-relaxed">
              언제나 실시간으로 응답합니다
            </p>
          </div>

          <div className="bg-white p-6 sm:p-8 md:p-10 rounded-2xl shadow-lg hover:shadow-2xl hover:-translate-y-2 transition-all">
            <div className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 bg-lavender rounded-2xl flex items-center justify-center mb-4 md:mb-6">
              <FileText size={24} className="text-white sm:w-7 sm:h-7 md:w-8 md:h-8" />
            </div>
            <h3 className="text-lg sm:text-xl md:text-2xl font-bold mb-3 md:mb-4 text-dark-navy">실제 공공 데이터</h3>
            <p className="text-sm sm:text-base text-gray-purple leading-relaxed">
              공공기관의 실제 분쟁조정 사례를 기반으로 안내합니다
            </p>
          </div>

          <div className="bg-white p-6 sm:p-8 md:p-10 rounded-2xl shadow-lg hover:shadow-2xl hover:-translate-y-2 transition-all">
            <div className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 bg-mint-green rounded-2xl flex items-center justify-center mb-4 md:mb-6">
              <MessageSquare size={24} className="text-white sm:w-7 sm:h-7 md:w-8 md:h-8" />
            </div>
            <h3 className="text-lg sm:text-xl md:text-2xl font-bold mb-3 md:mb-4 text-dark-navy">커뮤니티를 통한 경험 공유</h3>
            <p className="text-sm sm:text-base text-gray-purple leading-relaxed">
              실제 소비자들의 분쟁 해결 경험을 공유하고 배웁니다
            </p>
          </div>
        </div>
      </div>

      {/* Stats Section */}
      <div className="bg-ivory px-4 sm:px-6 md:px-8 pb-8 md:pb-16">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 md:gap-8 bg-dark-navy p-6 sm:p-8 md:p-12 rounded-2xl text-white max-w-6xl mx-auto">
          <div className="text-center">
            <div className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-mint-green mb-1 md:mb-2">무료</div>
            <div className="text-xs sm:text-sm md:text-base opacity-80">AI 상담 비용</div>
          </div>
          <div className="text-center">
            <div className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-mint-green mb-1 md:mb-2">즉시</div>
            <div className="text-xs sm:text-sm md:text-base opacity-80">24/7 실시간 상담</div>
          </div>
          <div className="text-center">
            <div className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-mint-green mb-1 md:mb-2">유일</div>
            <div className="text-xs sm:text-sm md:text-base opacity-80">소비자 커뮤니티</div>
          </div>
        </div>
      </div>

      {/* Bell 캐릭터 인터랙션 섹션 (맨 아래) */}
      <div className="bg-ivory px-4 sm:px-6 md:px-8 py-12 md:py-20">
        <div
          ref={bellContainerRef}
          className="flex flex-col items-center cursor-pointer select-none max-w-md mx-auto"
          onMouseMove={handlePet}
          onTouchMove={handlePet}
          onMouseLeave={handleMouseLeave}
        >
          {/* 상단 안내 텍스트 */}
          <p className="text-lg md:text-xl text-deep-teal font-semibold mb-4">
            저를 쓰다듬어 주세요!
          </p>

          {/* Bell 이미지 컨테이너 */}
          <div className="relative w-48 h-48 md:w-64 md:h-64 lg:w-80 lg:h-80">
            {/* 화난 벨 (기본) */}
            <img
              src={bell1}
              alt="화난 벨"
              className={`absolute inset-0 w-full h-full object-contain transition-all duration-500 ease-out ${
                isHappy ? 'opacity-0 scale-90' : 'opacity-100 scale-100'
              }`}
              style={{
                filter: !isHappy && petCount > 0 ? `brightness(${1 + petCount * 0.05})` : 'none',
              }}
            />
            {/* 웃는 벨 (쓰다듬은 후) */}
            <img
              src={bell2}
              alt="웃는 벨"
              className={`absolute inset-0 w-full h-full object-contain transition-all duration-500 ease-out ${
                isHappy ? 'opacity-100 scale-110' : 'opacity-0 scale-90'
              }`}
              style={{
                filter: isHappy ? 'drop-shadow(0 0 30px rgba(142, 207, 192, 0.6))' : 'none',
              }}
            />
          </div>

          {/* 하단 상태 텍스트 */}
          <p className="mt-4 text-base md:text-lg font-bold" style={{ color: '#243762' }}>
            {isHappy ? '상담 받은 후의 모습' : '상담 받기 전의 모습'}
          </p>

          {/* 진행 바 (쓰다듬기 전에만 표시) */}
          {!isHappy && (
            <div className="mt-3 w-48 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-deep-teal to-mint-green transition-all duration-200 rounded-full"
                style={{ width: `${(petCount / petThreshold) * 100}%` }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
