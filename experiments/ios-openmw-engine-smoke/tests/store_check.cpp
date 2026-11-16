#include "EngineIndex.hpp"
#include "LabelDispatch.hpp"
#include <components/esm3/loadbook.hpp>
#include <components/esm/luascripts.hpp>
#include <cstdio>
#include <iostream>
#include <algorithm>
#include <stdexcept>

namespace {
unsigned checks=0;
void require(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
int coreCalls=0,khrCalls=0;
void core(){++coreCalls;}
void khr(){++khrCalls;}
template<class F> void rejected(F action,const char* expected){
    try{action();}catch(const std::exception& e){require(std::string(e.what()).find(expected)!=std::string::npos,"Wrong exception diagnostic");return;}
    throw std::runtime_error("Expected explicit rejection missing");
}
void labels(){
    using G5::LabelAPI;using G5::labelAPI;using G5::selectLabel;
    require(labelAPI(true,3,0,true)==LabelAPI::KHR,"ES3.0 must use KHR");
    require(labelAPI(true,3,1,true)==LabelAPI::KHR,"ES3.1 must use KHR");
    require(labelAPI(true,3,2,false)==LabelAPI::Core,"ES3.2 core labels");
    require(labelAPI(true,3,0,false)==LabelAPI::None,"No advertised extension");
    require(labelAPI(false,4,3,false)==LabelAPI::Core,"Desktop4.3 core labels");
    require(labelAPI(false,4,1,true)==LabelAPI::KHR,"Desktop KHR uses unsuffixed entry");
    require(selectLabel(LabelAPI::None,&core,&khr)==nullptr,"Unsupported labels must not dispatch");
    selectLabel(labelAPI(true,3,0,true),&core,&khr)();
    require(coreCalls==0&&khrCalls==1,"ES3.0 exported core symbol must not be invoked");
    selectLabel(labelAPI(true,3,2,true),&core,&khr)();
    require(coreCalls==1&&khrCalls==1,"ES3.2 core dispatch");
    rejected([]{G5::selectLabel<void(*)()>(LabelAPI::KHR,&core,nullptr);},"entry point");
    rejected([]{G5::selectLabel<void(*)()>(LabelAPI::Core,nullptr,&khr);},"entry point");
    rejected([]{G5::labelAPI(true,0,0,true);},"invalid actual GL version");
}
}
int main(int argc,char** argv){
    auto* original=std::cout.rdbuf(std::cerr.rdbuf());
    try{
        if(argc<3)throw std::runtime_error("directory case [ordered private plugins] required");
        const std::filesystem::path root=argv[1];const std::string mode=argv[2];
        labels();
        std::vector<std::filesystem::path> content{root/"Morrowind.esm"};
        if(argc>3 && mode!="private-inspect")throw std::runtime_error("Additional content requires explicit private inspection mode");
        for(int i=3;i<argc;++i){
            const std::filesystem::path name=argv[i];
            if(name.has_parent_path()||name.is_absolute())throw std::runtime_error("Private content argument must be a filename");
            content.push_back(root/name);
        }
        if(std::filesystem::is_regular_file(root/"Authored.esp"))content.push_back(root/"Authored.esp");
        if(mode=="empty-content")content.clear();
        if(mode=="duplicate-content")content.push_back(content.front());
        if(mode=="load-order")std::reverse(content.begin(),content.end());
        G5::EngineIndex index(content);
        const auto id=ESM::RefId::stringRefId("g5_book");
        if(mode=="private-inspect"){
            require(index.store().get<ESM::NPC>().getSize()>1000,"Original NPC metadata missing");
            require(index.store().get<ESM::Book>().getSize()>100,"Original book metadata missing");
            require(index.cells.getSize()>1000,"Original CELL metadata missing");
            require(index.base(ESM::RefId::stringRefId("furn_de_rug_02")).type=="STAT","Original STAT lookup");
        }else{
            const auto* book=index.store().get<ESM::Book>().search(id);
            if(mode=="delete")require(!book&&index.store().find(id)==0,"Genuine engine deletion/index mismatch");
            else{
                require(book!=nullptr,"Previously excluded BOOK metadata missing");
                require(book->mData.mValue==(mode=="override"?42:7),"Genuine plugin/ignored record semantics");
                require(index.store().find(id)==ESM::REC_BOOK,"Native engine ID/type index");
                require(index.base(id).type=="BOOK"&&index.base(id).model.empty(),"Metadata must not silently activate gameplay objects");
            }
            if(mode.starts_with("lua")){
                const auto cfg=index.store().getLuaScriptsCfg();
                require(cfg.mScripts.size()==1&&cfg.mScripts[0].mRefs.size()==1,"Genuine Lua configuration lost");
                require(cfg.mScripts[0].mRefs[0].mRefnumContentFile==0,"Lua master reference remapping");
                std::string expected("\0\2\1",3);
                if(mode=="lua-table")expected=std::string("\0\3\x21x\2\1\4",7);
                if(mode=="lua-refnum"){
                    const char reference[]={0,char(0xc0),'o',23,0,0,0,0,0,0,0};
                    expected=std::string(reference,sizeof(reference));
                }
                require(cfg.mScripts[0].mInitializationData==expected,"Genuine Lua serialization/reference round trip");
            }
        }
        std::printf("{\"status\":\"PASS\",\"checks\":%u,\"cells\":%zu,\"books\":%zu,\"npcs\":%zu,\"scope\":\"genuine ESMStore CPU metadata and dispatch; no device rendering acceptance\"}\n",
            checks,index.cells.getSize(),index.store().get<ESM::Book>().getSize(),index.store().get<ESM::NPC>().getSize());
        std::cout.rdbuf(original);return 0;
    }catch(const std::exception& e){std::cerr<<"G5 stage=EngineIndex/ESMStore: "<<e.what()<<'\n';std::cout.rdbuf(original);return 1;}
}
