#include "StartupChecks.hpp"
int main(){
    try{
        const auto checks=G4Test::startupChecks();
        std::printf("{\"status\":\"PASS\",\"checks\":%u,\"scope\":\"genuine pinned OSG headless startup guards\"}\n",checks);
        return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"%s\n",error.what());return 1;
    }
}
