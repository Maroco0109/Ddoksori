import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/shared/config/routes';
import { useChatStore } from '@/features/chat/chat.store';

import procedure1 from '@/shared/assets/icons/procedure-1.png';
import procedure2 from '@/shared/assets/icons/procedure-2.png';
import procedure3 from '@/shared/assets/icons/procedure-3.png';
type Committee = {
  title: string;
  subtitle: string;
  image: string;
};

export default function ProcedurePage() {
  const [selectedImage, setSelectedImage] = useState<Committee | null>(null);
  const navigate = useNavigate();
  const startNewChat = useChatStore((state) => state.startNewChat);
  const procedures = [
    {
      step: 1,
      title: '분쟁 유형 확인',
      description: '일반적 소비자 거래, 개인 간의 중고 거래, 콘텐츠 거래, 그 외 특수분야 거래 중 해당 유형을 파악합니다.',
      details: ['상품/서비스 내용 확인', '피해 내역 정리']
    },
    {
      step: 2,
      title: '증거 자료 수집',
      description: '분쟁 해결에 필요한 증거 자료를 준비합니다.',
      details: ['거래 내역서, 영수증', '대화 캡처 이미지', '제품 사진/영상', '배송 정보 등']
    },
    {
      step: 3,
      title: '조정 신청 제출',
      description: '해당 분쟁조정위원회에 온라인으로 신청합니다.',
      details: ['소비자분쟁조정위원회', '전자거래분쟁조정위원회', '콘텐츠분쟁조정위원회', '그 외 기타 분쟁조정위원회']
    },
    {
      step: 4,
      title: '조정 진행',
      description: '평균 1~2개월 이내 조정 결과가 통보됩니다. 단, 내용이 복잡할 경우 6개월까지 소요될 수 있습니다.',
      details: ['신청서 검토', '당사자 의견 청취', '조정안 작성 및 통보']
    },
    {
      step: 5,
      title: '조정안 수락',
      description: '양측이 조정안을 수락하면 법적 효력이 발생합니다.',
      details: [<>양측이 조정안을 수락하면 <strong>재판상 화해(판결문)</strong>와 동일한 효력을 갖습니다.</>, '단, 한 쪽이라도 거부하면 민사소송으로 진행해야 합니다.']
    }
  ];

  const committees = [
    {
      title: '한국소비자원',
      subtitle: '소비자분쟁조정위원회',
      image: procedure1
    },
    {
      title: '한국인터넷진흥원',
      subtitle: '전자거래분쟁조정위원회',
      image: procedure2
    },
    {
      title: '한국콘텐츠진흥원',
      subtitle: '콘텐츠분쟁조정위원회',
      image: procedure3
    }
  ];

  return (
    <div className="procedure-page">
      {/* Custom scrollbar styles for modal */}
      <style>{`
        .modal-scrollbar::-webkit-scrollbar {
          width: 8px;
        }
        .modal-scrollbar::-webkit-scrollbar-track {
          background: #f0f0f0;
          border-radius: 10px;
        }
        .modal-scrollbar::-webkit-scrollbar-thumb {
          background: #0d9488;
          border-radius: 10px;
        }
        .modal-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #0f766e;
        }
      `}</style>

      {/* Page Header */}
      <div className="mb-8 md:mb-12">
        <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold mb-3 md:mb-4 text-dark-navy">조정 신청 절차 안내</h1>
        <p className="text-base sm:text-lg md:text-xl text-gray-purple">
          단계별로 따라하시면 누구나 쉽게 조정을 신청할 수 있습니다
        </p>
      </div>

      {/* Timeline */}
      <div className="relative pl-8 md:pl-12 mb-8 md:mb-12">
        {/* 타임라인 라인 */}
        <div className="absolute left-3 md:left-4 top-0 bottom-0 w-0.5 md:w-1 bg-gradient-to-b from-deep-teal to-mint-green"></div>

        {procedures.map((proc, index) => (
          <div key={index}>
            <div className="relative mb-8 md:mb-12 flex gap-4 md:gap-8">
              {/* Step Number Circle */}
              <div className="absolute -left-7 md:-left-10 w-10 h-10 md:w-12 md:h-12 bg-deep-teal text-white rounded-full flex items-center justify-center font-extrabold text-lg md:text-xl shadow-lg shadow-deep-teal/40">
                {proc.step}
              </div>

              {/* Step Content */}
              <div className="bg-white p-4 sm:p-6 md:p-8 rounded-2xl flex-1 shadow-md">
                <h3 className="text-lg sm:text-xl md:text-2xl font-bold mb-2 md:mb-3 text-dark-navy">{proc.title}</h3>
                <p className="text-sm sm:text-base text-gray-purple mb-3 md:mb-4">{proc.description}</p>
                <ul className="space-y-1.5 md:space-y-2">
                  {proc.details.map((detail, i) => (
                    <li key={i} className="flex items-start">
                      <span className="text-deep-teal font-extrabold mr-2 md:mr-3">✓</span>
                      <span className="text-sm sm:text-base text-gray-purple">{detail}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* 공지사항 - Step 3 이후 표시 */}
            {proc.step === 3 && (
              <div className="relative mb-8 md:mb-12 flex gap-4 md:gap-8">
                <div className="bg-gradient-to-br from-amber-50 to-orange-50 border-l-4 border-amber-500 p-4 sm:p-6 md:p-8 rounded-2xl flex-1 shadow-md">
                  <div className="flex items-center gap-2 mb-3 md:mb-4">
                    <span className="text-xl sm:text-2xl">⚠️</span>
                    <h4 className="text-base sm:text-lg md:text-xl font-bold text-amber-700">안내사항</h4>
                  </div>
                  <p className="text-sm sm:text-base text-gray-700 font-semibold mb-3 md:mb-4">
                    똑소리는 소비자가 겪는 소액 분쟁에 특화된 서비스입니다.
                  </p>
                  <p className="text-sm sm:text-base text-gray-600 mb-3 md:mb-4">
                    위 3가지의 분쟁조정위원회 외에도 다양한 기관의 분쟁조정위원회가 존재하고 있습니다.
                    아래에 해당하는 좀 더 복잡하고 고도화된 분쟁은 관련 외부전문가의 상담을 받아보시길 바랍니다.
                  </p>
                  <div className="bg-white/60 rounded-xl p-3 sm:p-4 md:p-5">
                    <p className="text-xs sm:text-sm text-gray-500 mb-2 md:mb-3 font-medium">기타 분쟁조정위원회</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3">
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 bg-amber-500 rounded-full flex-shrink-0"></span>
                        <span className="text-xs sm:text-sm text-gray-700">금융감독원 · <span className="text-amber-700 font-medium">금융분쟁조정위원회</span></span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 bg-amber-500 rounded-full flex-shrink-0"></span>
                        <span className="text-xs sm:text-sm text-gray-700">한국의료분쟁조정중재원 · <span className="text-amber-700 font-medium">의료분쟁조정위원회</span></span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 bg-amber-500 rounded-full flex-shrink-0"></span>
                        <span className="text-xs sm:text-sm text-gray-700">개인정보보호위원회 · <span className="text-amber-700 font-medium">개인정보분쟁조정위원회</span></span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 bg-amber-500 rounded-full flex-shrink-0"></span>
                        <span className="text-xs sm:text-sm text-gray-700">한국부동산원 · <span className="text-amber-700 font-medium">임대차분쟁조정위원회</span></span>
                      </div>
                      <div className="flex items-center gap-2 sm:col-span-2">
                        <span className="w-1.5 h-1.5 bg-amber-500 rounded-full flex-shrink-0"></span>
                        <span className="text-xs sm:text-sm text-gray-700">국토교통부 · <span className="text-amber-700 font-medium">건설/건축분쟁조정위원회</span> 등</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Dispute Resolution Committees */}
      <div className="mb-8 md:mb-12">
        <div className="flex flex-col sm:flex-row justify-between items-center mb-6 md:mb-8 gap-2 sm:gap-4">
          <h2 className="text-xl sm:text-2xl md:text-3xl font-bold text-dark-navy">
            분쟁조정위원회별 절차 안내
          </h2>
          <div className="flex items-center gap-2 bg-deep-teal/10 px-3 sm:px-4 py-2 rounded-full">
            <span className="text-deep-teal text-lg sm:text-xl">🔍</span>
            <p className="text-xs sm:text-sm text-deep-teal font-semibold whitespace-nowrap">
              각 카드 이미지를 클릭하면 이미지가 확대됩니다
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6 md:gap-8">
          {committees.map((committee, index) => (
            <div
              key={index}
              className="bg-white p-4 sm:p-6 md:p-8 rounded-2xl shadow-lg hover:shadow-2xl hover:-translate-y-2 transition-all"
            >
              <h3 className="text-base sm:text-lg md:text-xl font-bold mb-1 md:mb-2 text-deep-teal text-center">
                {committee.title}
              </h3>
              <p className="text-xs sm:text-sm md:text-base text-gray-purple mb-4 md:mb-6 text-center">
                {committee.subtitle}
              </p>
              <div className="flex justify-center items-center cursor-pointer" onClick={() => setSelectedImage(committee)}>
                <img
                  src={committee.image}
                  alt={`${committee.title} - ${committee.subtitle}`}
                  className="w-full h-auto object-contain rounded-lg hover:opacity-80 transition-opacity"
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Help Box */}
      <div className="bg-gradient-to-br from-lavender/20 to-mint-green/15 p-6 sm:p-8 md:p-10 rounded-2xl text-center">
        <h3 className="text-lg sm:text-xl md:text-2xl font-bold mb-3 md:mb-4 text-dark-navy">도움이 필요하신가요?</h3>
        <p className="text-sm sm:text-base text-gray-purple mb-4 md:mb-6">
          AI 상담 챗봇에게 물어보시면 맞춤형 안내를 받으실 수 있습니다
        </p>
        <button
          className="bg-deep-teal text-white px-6 sm:px-8 md:px-10 py-3 md:py-4 rounded-full text-sm sm:text-base font-semibold hover:bg-mint-green transform hover:-translate-y-1 transition-all"
          onClick={() => {
            startNewChat();
            navigate(ROUTES.CHAT);
          }}
        >
          AI 상담 시작하기
        </button>
      </div>

      {/* Image Modal */}
      {selectedImage && (
        <div
          className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 sm:p-6 md:p-8"
          onClick={() => setSelectedImage(null)}
        >
          <div
            className="modal-scrollbar relative max-w-6xl w-full max-h-[90vh] bg-white rounded-2xl p-4 sm:p-6 md:p-8 overflow-auto"
            style={{
              scrollbarColor: '#0d9488 #f0f0f0',
              scrollbarWidth: 'thin'
            }}
          >
            <button
              onClick={() => setSelectedImage(null)}
              className="absolute top-2 right-2 sm:top-4 sm:right-4 w-8 h-8 sm:w-10 sm:h-10 bg-deep-teal text-white rounded-full flex items-center justify-center hover:bg-mint-green transition-colors z-10"
            >
              ✕
            </button>
            <div className="text-center mb-4 sm:mb-6">
              <h3 className="text-lg sm:text-xl md:text-2xl font-bold mb-1 md:mb-2 text-deep-teal">
                {selectedImage.title}
              </h3>
              <p className="text-sm sm:text-base text-gray-purple">
                {selectedImage.subtitle}
              </p>
            </div>
            <div className="flex justify-center">
              <img
                src={selectedImage.image}
                alt={`${selectedImage.title} - ${selectedImage.subtitle}`}
                className="max-w-full h-auto object-contain"
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
