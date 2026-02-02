import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/shared/config/routes';
import { MessageCircle, FileText, MessageSquare } from 'lucide-react';
import { useChatStore } from '@/features/chat/chat.store';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';

gsap.registerPlugin(ScrollTrigger);

export default function HomePage() {
  const section1Ref = useRef<HTMLDivElement | null>(null);
  const section2Ref = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();
  const startNewChat = useChatStore((state) => state.startNewChat);

  useEffect(() => {
    // Lenis 스무스 스크롤 초기화
    const lenis = new Lenis({
      duration: 1.2,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
    });

    function raf(time: number) {
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
    <div className="main-page snap-y snap-mandatory">
      {/* 메인 히어로 섹션 - 첫 번째 이미지 */}
      <div
        ref={section1Ref}
        className="relative overflow-hidden"
      >
        {/* 배경 이미지 */}
        <img
          src="/web_main.png"
          alt="똑소리 메인 배경"
          className="w-full h-auto block"
        />

        {/* 텍스트 콘텐츠 - 이미지 상단에 절대 위치로 배치 */}
        <div
          ref={section2Ref}
          className="absolute top-0 left-0 right-0 text-center px-4 sm:px-6 md:px-8 pt-16 md:pt-24 z-10"
        >
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

      {/* 추가 배경 이미지들과 콘텐츠 영역 */}
      <div className="relative overflow-hidden">
        {/* 배경 이미지들 (반응형으로 개수 조절) */}
        {/* 두 번째 이미지 - 모든 화면 */}
        <img
          src="/web_main.png"
          alt="똑소리 배경"
          className="w-full h-auto block"
        />
        {/* 세 번째 이미지 - 태블릿 이하 (1024px 미만) */}
        <img
          src="/web_main.png"
          alt="똑소리 배경"
          className="w-full h-auto block lg:hidden"
        />
        {/* 네 번째 이미지 - 모바일만 (768px 미만) */}
        <img
          src="/web_main.png"
          alt="똑소리 배경"
          className="w-full h-auto block md:hidden"
        />

        {/* 콘텐츠를 이미지 위에 오버레이 */}
        <div className="absolute inset-0">
        {/* Features Grid */}
        <div className="px-4 sm:px-6 md:px-8 pt-4 md:pt-8 pb-8 md:pb-12">
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
              <div className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 rounded-2xl flex items-center justify-center mb-4 md:mb-6" style={{ backgroundColor: '#ebccb5' }}>
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
        <div className="px-4 sm:px-6 md:px-8 pb-8 md:pb-16">
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
        </div>
      </div>

    </div>
  );
}
